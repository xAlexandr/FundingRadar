// service.go
package main

import (
	"bytes"
	"compress/zlib"
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"log"
	"math"
	"net/http"
	"os"
	"runtime"
	"sort"
	"strconv"
	"strings"
	"sync/atomic"
	"sync"
	"time"

	_ "github.com/go-sql-driver/mysql"
	jsoniter "github.com/json-iterator/go"
	"github.com/redis/go-redis/v9"
)

var (
	ctx      = context.Background()
	jsonFast = jsoniter.ConfigFastest

	redisAddr = getEnv("REDIS_ADDR", "localhost:6379")
	mysqlDsn  = getEnv("MYSQL_DSN", "")
	port      = getEnv("PORT", "8081")

	rdb0 *redis.Client
	rdb1 *redis.Client
	rdb2 *redis.Client
	db   *sql.DB

	redisMu sync.Mutex
	dbMu    sync.Mutex
)

var notifPending [3]int32 // index 0 -> spreads, 1 -> spotfutures, 2 -> dex

var processingInProgress int32 = 0 // 0 - idle, 1 - running
// constants
const (
	FOUR_HOURS_SECONDS  = 4 * 60 * 60
	MAX_ENTRIES         = 300
	MAX_COMPRESSED_SIZE = 60000
	NOTIF_LIST_LIMIT    = 10000
)

var (
	// caches protected by cacheMu
	cacheMu sync.RWMutex

	cacheSpreads     []Spread
	cacheSpreadsTime time.Time

	cacheSpots     []SpotFuture
	cacheSpotsTime time.Time

	cacheDex     []Dex
	cacheDexTime time.Time

	cacheUsers     []User
	cacheUsersTime time.Time

	// BinanceAlpha contracts cache: symbol -> {contract_address, chain_name, alpha_id}
	cacheBAContracts     map[string]map[string]string
	cacheBAContractsTime time.Time

	cacheInterval = 2 * time.Second // re-cache every 2 seconds
)

var (
    cacheSpreadsAtomic atomic.Value // stores []Spread
    cacheSpotsAtomic   atomic.Value // stores []SpotFuture
    cacheDexAtomic     atomic.Value // stores []Dex
    cacheUsersAtomic   atomic.Value
)

// Top-funding cached results (rebuilt on every reload)
var (
    cacheTopFundingAtomic     atomic.Value // stores []coinFundingResult
    cacheTopFundingSpotAtomic atomic.Value // stores []coinFundingSpotResult
)

type coinFundingResult struct {
    Symbol   string  `json:"symbol"`
    Market1  string  `json:"market1"`
    Market2  string  `json:"market2"`
    Funding1 float64 `json:"funding1"`
    Funding2 float64 `json:"funding2"`
    Spread   float64 `json:"spread"`
    Entry    float64 `json:"entry"`
}

type coinFundingSpotResult struct {
    Symbol   string  `json:"symbol"`
    Market1  string  `json:"market1"`
    Market2  string  `json:"market2"`
    Funding2 float64 `json:"funding2"`
    Spread   float64 `json:"spread"`
    Entry    float64 `json:"entry"`
}

// expanded spread (holds pointer to original Spread to avoid copying big struct)
type expandedSpread struct {
    S        *Spread
    Dir      string  // "normal" or "reverse"
    Primary  float64 // primary metric used for sorting in this view
    Secondary float64 // tie-breaker
}

// dexEntry is used for dedup and sorting in DEX API handlers
type dexEntry struct {
	d         Dex
	primary   float64
	secondary float64
}

type TwoSortedSpreadsExpanded struct {
    BySpread []expandedSpread // primary = takeSecondReverse (spread / funding diff)
    ByCourse []expandedSpread // primary = checkSpreadFutures (entry)
}

// atomic holders for expanded pre-sorted views
var cacheSpreadsExpanded atomic.Value // stores *TwoSortedSpreadsExpanded

// expanded spot (pointer to avoid copying)
type expandedSpot struct {
    S         *SpotFuture
    Primary   float64 // primary metric for sorting (either spread or course)
    Secondary float64 // tie-breaker
}

type TwoSortedSpots struct {
    BySpread []expandedSpot // primary = Spread
    ByCourse []expandedSpot // primary = Course (entry)
}

var cacheSpotsExpanded atomic.Value // stores *TwoSortedSpots

// TwoSortedDex holds pre-sorted DEX views (mirrors TwoSortedSpreadsExpanded pattern).
type TwoSortedDex struct {
    ByFunding []dexEntry // primary = FundingRate (desc), secondary = Diff
    ByDiff    []dexEntry // primary = Diff (desc), secondary = FundingRate
}

var cacheDexExpanded atomic.Value // stores *TwoSortedDex

// ------------------- DATA STRUCTS -------------------

type Spread struct {
	Symbol         string  `json:"symbol"`
	Market1        string  `json:"market1"`
	Market2        string  `json:"market2"`
	Market1Funding float64 `json:"market1funding"`
	Market2Funding float64 `json:"market2funding"`
	Market1Time    float64 `json:"market1time"`
	Market2Time    float64 `json:"market2time"`
	Market1Bid     float64 `json:"market1bid"`
	Market2Bid     float64 `json:"market2bid"`
	Market1Fee     float64 `json:"market1fee"`
	Market2Fee     float64 `json:"market2fee"`
	Market1Predict string  `json:"market1predict"`
	Market2Predict string  `json:"market2predict"`
	Spread         float64 `json:"spread"`
	IsNew          string  `json:"isNew"`
	IsUpdated      string  `json:"isUpdated"`
	IsDeviation1   float64 `json:"isDeviation1"`
	IsDeviation2   float64 `json:"isDeviation2"`
	Market1Ask     float64 `json:"market1ask"`
	Market2Ask     float64 `json:"market2ask"`
	M1h1           string  `json:"m1h1"`
	M1h3           string  `json:"m1h3"`
	M1h7           string  `json:"m1h7"`
	M1h30          string  `json:"m1h30"`
	M2h1           string  `json:"m2h1"`
	M2h3           string  `json:"m2h3"`
	M2h7           string  `json:"m2h7"`
	M2h30          string  `json:"m2h30"`
	Amount24M1     float64 `json:"amount24m1"`
	Amount24M2     float64 `json:"amount24m2"`
	LimitsM1       float64 `json:"limitsm1"`
	LimitsM2       float64 `json:"limitsm2"`
}

type SpotFuture struct {
	Symbol         string  `json:"symbol"`
	Market1        string  `json:"market1"`
	Market2        string  `json:"market2"`
	Market2Funding float64 `json:"market2funding"`
	Market2Time    float64 `json:"market2time"`
	Market2Bid     float64 `json:"market2bid"`
	Market1Fee     float64 `json:"market1fee"`
	Market2Fee     float64 `json:"market2fee"`
	Market2Predict string  `json:"market2predict"`
	Spread         float64 `json:"spread"`
	IsNew          string  `json:"isNew"`
	IsUpdated      string  `json:"isUpdated"`
	IsDeviation2   float64 `json:"isDeviation2"`
	Spot1Bid       float64 `json:"spot1bid"`
	Market2Ask     float64 `json:"market2ask"`
	Spot1Ask       float64 `json:"spot1ask"`
	M2h1           string  `json:"m2h1"`
	M2h3           string  `json:"m2h3"`
	M2h7           string  `json:"m2h7"`
	M2h30          string  `json:"m2h30"`
	Amount24M2     float64 `json:"amount24m2"`
	LimitsM2       float64 `json:"limitsm2"`
	Amount24Spot   float64 `json:"amount24spot"`
}

type Dex struct {
	Symbol      string  `json:"symbol"`
	Market2     string  `json:"market2"`
	Bid         float64 `json:"bid"`
	PriceUsd    float64 `json:"priceUsd"`
	Diff        float64 `json:"diff"`
	Contract    string  `json:"contract"`
	Chain       string  `json:"chain"`
	Volume24    float64 `json:"volume24"`
	Volume24Cex float64 `json:"volume24_cex"`
	DexId       string  `json:"dexId"`
	URL         string  `json:"url"`
	CexAsk      float64 `json:"cex_ask"`
	FundingRate float64 `json:"funding_rate"`
	IsUpdated   string  `json:"isUpdated"`
}

// User as returned by loadUsers (parsed fields)
type User struct {
	Tgid               string
	Username           string
	DataSearch         map[string]interface{}
	ListMarketsFutures map[string]int
	ListMarketsSpot    map[string]int
	Blacklist          map[string]struct{}
	DexBlacklist       map[string]struct{}
	LastCoins          map[string]time.Time
	RawLastNotice      []byte
	IsActive           string
	IsActiveAdmin      string
	TestActive         string
}

// notification wrappers
type spreadNotification struct {
	Spread
	Reverse bool   `json:"reverse"`
	Tgid    string `json:"tgid"`
}
type spotNotification struct {
	SpotFuture
	Tgid string `json:"tgid"`
}
type dexNotification struct {
	Dex
	Tgid string `json:"tgid"`
}

// ------------------- CONCURRENCY POOLS -------------------

type MetricSpot struct {
	S          SpotFuture
	CourseVal  float64
	SpreadVal  float64
	MetricSort float64
}
var metricSpotPool = sync.Pool{
	New: func() any { return make([]MetricSpot, 0, 4096) },
}
var spotWorkPool = make(chan struct{}, runtime.NumCPU()*2)
var spreadWorkPool = make(chan struct{}, runtime.NumCPU()*2)


var marketsOrder = []string{
	"Bybit", "Mexc", "Kucoin", "Gateio", "Bitget",
	"Huobi", "Okx", "Binance", "BingX", "BitMart",
	"Ourbit", "Hyperliquid", "LBank", "DEX", "Aster",
	"XT", "WEEX", "Phemex",
}

// ------------------- STARTUP / CONNECTIONS -------------------

func initRedisClients() error {
	redisMu.Lock()
	defer redisMu.Unlock()

	for {
		rdb0 = redis.NewClient(&redis.Options{Addr: redisAddr, DB: 0})
		rdb1 = redis.NewClient(&redis.Options{Addr: redisAddr, DB: 1})
		rdb2 = redis.NewClient(&redis.Options{Addr: redisAddr, DB: 2})

		var errs []string
		if err := rdb0.Ping(ctx).Err(); err != nil {
			errs = append(errs, fmt.Sprintf("rdb0: %v", err))
		}
		if err := rdb1.Ping(ctx).Err(); err != nil {
			errs = append(errs, fmt.Sprintf("rdb1: %v", err))
		}
		if err := rdb2.Ping(ctx).Err(); err != nil {
			errs = append(errs, fmt.Sprintf("rdb2: %v", err))
		}
		if len(errs) == 0 {
			log.Println("✅ Redis connected")
			return nil
		}
		log.Printf("⚠️ Redis connect failed: %s (retrying in 5s)", strings.Join(errs, "; "))
		time.Sleep(5 * time.Second)
	}
}

func initDB() error {
	dbMu.Lock()
	defer dbMu.Unlock()
	for {
		var err error
		db, err = sql.Open("mysql", mysqlDsn)
		if err != nil {
			log.Printf("MySQL open failed: %v (retrying in 5s)", err)
			time.Sleep(5 * time.Second)
			continue
		}
		if err = db.Ping(); err != nil {
			log.Printf("MySQL ping failed: %v (retrying in 5s)", err)
			time.Sleep(5 * time.Second)
			continue
		}
		db.SetMaxOpenConns(20)
		db.SetMaxIdleConns(5)
		db.SetConnMaxLifetime(5 * time.Minute)
		log.Println("✅ MySQL connected")
		return nil
	}
}

func ensureRedisByIndex(idx int) *redis.Client {
	redisMu.Lock()
	defer redisMu.Unlock()
	switch idx {
	case 0:
		if rdb0 == nil {
			rdb0 = redis.NewClient(&redis.Options{Addr: redisAddr, DB: 0})
		}
		return rdb0
	case 1:
		if rdb1 == nil {
			rdb1 = redis.NewClient(&redis.Options{Addr: redisAddr, DB: 1})
		}
		return rdb1
	case 2:
		if rdb2 == nil {
			rdb2 = redis.NewClient(&redis.Options{Addr: redisAddr, DB: 2})
		}
		return rdb2
	default:
		if rdb0 == nil {
			rdb0 = redis.NewClient(&redis.Options{Addr: redisAddr, DB: 0})
		}
		return rdb0
	}
}

func ensureDB() *sql.DB {
	dbMu.Lock()
	defer dbMu.Unlock()
	if db == nil {
		_ = initDB()
	}
	// best-effort ping
	if db != nil {
		if err := db.Ping(); err != nil {
			_ = initDB()
		}
	}
	return db
}

// Generic load typed from redis client by key
func loadRedisKeyFromClient[T any](client *redis.Client, key string) ([]T, error) {
	if client == nil {
		return nil, fmt.Errorf("redis client nil")
	}
	raw, err := client.Get(ctx, key).Bytes()
	if err != nil {
		if err == redis.Nil {
			return []T{}, nil
		}
		return nil, err
	}
	var out []T
	if err := jsonFast.Unmarshal(raw, &out); err != nil {
		return nil, err
	}
	return out, nil
}

// ------------------- LOAD USERS (only used by cacher) -------------------

// loadUsers reads Users table and returns parsed User[] with maps/sets.
// This function will be called only by background cacher (every 2s).
func loadUsers() ([]User, error) {
	dbc := ensureDB()
	if dbc == nil {
		return nil, fmt.Errorf("mysql unavailable")
	}
	rows, err := dbc.Query("SELECT tgid, username, dataSearch, listMarketsFutures, listMarketsSpot, blacklist, information, lastNoticeCoins, isActive, isActiveAdmin, testActive FROM Users")
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var users []User
	for rows.Next() {
		var tgid sql.NullString
		var username sql.NullString
		var dataSearchStr sql.NullString
		var marketsFutStr sql.NullString
		var marketsSpotStr sql.NullString
		var blacklistRaw []byte
		var informationRaw []byte
		var rawLastNotice []byte
		var isActive sql.NullString
		var isActiveAdmin sql.NullString
		var testActive sql.NullString

		if err := rows.Scan(&tgid, &username, &dataSearchStr, &marketsFutStr, &marketsSpotStr, &blacklistRaw, &informationRaw, &rawLastNotice, &isActive, &isActiveAdmin, &testActive); err != nil {
			log.Println("Row scan error:", err)
			continue
		}

		dataSearch := parseJSONMap(dataSearchStr.String)
		marketsFut := parseMarketString(marketsFutStr.String)
		marketsSpot := parseMarketString(marketsSpotStr.String)
		blacklist := parseCompressedSet(blacklistRaw)
		dexBlacklist := parseCompressedSet(informationRaw)
		lastCoins := parseLastCoins(rawLastNotice)

		u := User{
			Tgid:               strings.TrimSpace(tgid.String),
			Username:           username.String,
			DataSearch:         dataSearch,
			ListMarketsFutures: marketsFut,
			ListMarketsSpot:    marketsSpot,
			Blacklist:          blacklist,
			DexBlacklist:       dexBlacklist,
			LastCoins:          lastCoins,
			RawLastNotice:      rawLastNotice,
			IsActive:           isActive.String,
			IsActiveAdmin:      isActiveAdmin.String,
			TestActive:         testActive.String,
		}
		users = append(users, u)
	}
	return users, nil
}

// ------------------- PUB/SUB subscriber + reload functions -------------------
// ------------------- CACHER (background) -------------------
// debounce window: coalesce multiple updates that happen within this time
const reloadDebounce = 250 * time.Millisecond

var lastHandledMu sync.Mutex
var lastHandled = map[string]time.Time{}

// reload mutexes to avoid concurrent reloads of same resource
var (
	reloadSpreadsMu sync.Mutex
	reloadSpotsMu   sync.Mutex
	reloadDexMu     sync.Mutex
	reloadUsersMu   sync.Mutex
)

// ------------------- NEW: Sync all 3 cache updates before notifications -------------------
var syncMu sync.Mutex
var cacheUpdated = struct {
    spreads bool
    spots   bool
}{}

func markCacheUpdated(which string) {
    syncMu.Lock()
    defer syncMu.Unlock()

    switch which {
    case "spreads":
        cacheUpdated.spreads = true
    case "spots":
        cacheUpdated.spots = true
    }

    // если все три кэша обновились — запускаем runProcessingCycle
    if cacheUpdated.spreads && cacheUpdated.spots {
      //  log.Println("✅ All caches updated — running processing cycle")
        go runProcessingCycle()

        // сбрасываем флаги, чтобы ждать следующего полного обновления
        cacheUpdated.spreads = false
        cacheUpdated.spots = false
    }
}



// startRedisSubscriber subscribes to update channels and reloads caches immediately.
func startRedisSubscriber(ctx context.Context) {
	client := ensureRedisByIndex(0)
	if client == nil {
		log.Println("startRedisSubscriber: redis client nil")
		return
	}
	pubsub := client.Subscribe(ctx, "Spreads:update", "SpotFutures:update", "Dex:update", "Users:update")
	// wait for subscription to be created
	_, err := pubsub.Receive(ctx)
	if err != nil {
		log.Printf("startRedisSubscriber: subscribe failed: %v", err)
		return
	}
	ch := pubsub.Channel()
	log.Println("startRedisSubscriber: listening for updates (Spreads/SpotFutures/Dex/Users)")

	for {
		select {
		case <-ctx.Done():
			_ = pubsub.Close()
			return
		case msg, ok := <-ch:
			if !ok {
				// channel closed
				_ = pubsub.Close()
				return
			}
			if msg == nil {
				continue
			}
			channel := msg.Channel
			now := time.Now()

			// debounce per channel to avoid thrashing
			lastHandledMu.Lock()
			last := lastHandled[channel]
			if now.Sub(last) < reloadDebounce {
				lastHandledMu.Unlock()
				continue
			}
			lastHandled[channel] = now
			lastHandledMu.Unlock()

			// handle channel
			switch channel {
			case "Spreads:update":
				go func() {
					if err := reloadSpreadsFromRedis(); err != nil {
						log.Printf("reloadSpreadsFromRedis error: %v", err)
					} else {
                        markCacheUpdated("spreads")
                    }
					// reload users once per batch if needed (coalesce)
					tryReloadUsersCoalesced()
				}()
			case "SpotFutures:update":
				go func() {
					if err := reloadSpotsFromRedis(); err != nil {
						log.Printf("reloadSpotsFromRedis error: %v", err)
					}  else {
                        markCacheUpdated("spots")
                    }
					tryReloadUsersCoalesced()
				}()
			case "Dex:update":
				go func() {
					if err := reloadDexFromRedis(); err != nil {
						log.Printf("reloadDexFromRedis error: %v", err)
					}
					tryReloadUsersCoalesced()
				}()
			case "Users:update":
				go func() {
					if err := reloadUsersFromDB(); err != nil {
						log.Printf("reloadUsersFromDB error: %v", err)
					}
				}()
			default:
				// ignore
			}
		}
	}
}

// tryReloadUsersCoalesced reloads users but prevents many reloads in a short window.
func tryReloadUsersCoalesced() {
	// debounce users separately to avoid 3 reloads when writer sets 3 keys
	lastHandledMu.Lock()
	last := lastHandled["Users:coalesce"]
	now := time.Now()
	if now.Sub(last) < reloadDebounce {
		lastHandledMu.Unlock()
		return
	}
	lastHandled["Users:coalesce"] = now
	lastHandledMu.Unlock()

	go func() {
		if err := reloadUsersFromDB(); err != nil {
			log.Printf("reloadUsersFromDB error: %v", err)
		}
	}()
}

// ------------------- reload helpers -------------------
// runProcessingCycle запускает один цикл обработки пользователей (как fundingBotLoop одного тикера)
func runProcessingCycle() {
    // prevent overlapping cycles
    if !atomic.CompareAndSwapInt32(&processingInProgress, 0, 1) {
        return
    }
    go func() {
        defer atomic.StoreInt32(&processingInProgress, 0)

        start := time.Now()
        users := getCachedUsers()
        users = filterActiveUsersBot(users)
        users = filterMonitoringUsers(users)
        spreads := getCachedSpreads()
        spots := getCachedSpots()
        dex := getCachedDex()

        var wg sync.WaitGroup
        for i := range users {
            wg.Add(1)
            u := &users[i]
            go func(u *User) {
                defer wg.Done()
                processUser(u, spreads, spots, dex)
            }(u)
        }
        wg.Wait()
        log.Printf("runProcessingCycle: done in %.2f ms (users=%d)", float64(time.Since(start).Milliseconds()), len(users))

        // After processing — publish single-flush notifications for python if there were pushes
        publishAggregatedFlush()

    }()
}

// publishAggregatedFlush — publish one consolidated "flush" message to a single channel (DB0).
// Payload contains timestamp and list of DB indexes that had pending notifications.
// After publish we reset pending flags for those DBs.
func publishAggregatedFlush() {
    // collect which DBs have pending notifications
    dbs := make([]int, 0, 3)
    for i := 0; i < 3; i++ {
        if atomic.LoadInt32(&notifPending[i]) == 1 {
            dbs = append(dbs, i)
        }
    }
    if len(dbs) == 0 {
        return
    }

    // build payload { "ts": <unix>, "dbs": [0,1] }
    payload := map[string]interface{}{
        "ts":  time.Now().Unix(),
        "dbs": dbs,
    }
    b, err := jsonFast.Marshal(payload)
    if err != nil {
        // best-effort: still reset flags to avoid duplicate flush storms
        for _, i := range dbs {
            atomic.StoreInt32(&notifPending[i], 0)
        }
        log.Printf("publishAggregatedFlush: marshal error: %v", err)
        return
    }

    // publish on DB0 (single channel). Use ensureRedisByIndex(0)
    client := ensureRedisByIndex(0)
    if client == nil {
        // reset flags to avoid spam if redis dead
        for _, i := range dbs {
            atomic.StoreInt32(&notifPending[i], 0)
        }
        log.Printf("publishAggregatedFlush: redis db0 nil, flags reset")
        return
    }

    // best-effort publish
    if err := client.Publish(ctx, "NotificationsPub:Flush", b).Err(); err != nil {
        log.Printf("publishAggregatedFlush: publish failed: %v", err)
        // still reset flags to avoid endless retries
    }

    // reset flags for DBs we reported
    for _, i := range dbs {
        atomic.StoreInt32(&notifPending[i], 0)
    }
}

// reloadSpreadsFromRedis loads "Spreads:all", stores atomically and rebuilds expanded sorted views.
func reloadSpreadsFromRedis() error {
	reloadSpreadsMu.Lock()
	defer reloadSpreadsMu.Unlock()

	client := ensureRedisByIndex(0)
	if client == nil {
		return fmt.Errorf("redis client db0 nil")
	}
	raw, err := client.Get(ctx, "Spreads:all").Bytes()
	if err != nil {
		return fmt.Errorf("get Spreads:all: %w", err)
	}
	var sps []Spread
	if err := jsonFast.Unmarshal(raw, &sps); err != nil {
		return fmt.Errorf("unmarshal spreads: %w", err)
	}

	// build expanded entries (pointers into sps)
	exp := make([]expandedSpread, 0, len(sps)*2)
	for i := range sps {
		sp := &sps[i]
		// normal
		exp = append(exp, expandedSpread{
			S:         sp,
			Dir:       "normal",
			Primary:   takeSecondReverse(*sp, "normal"),
			Secondary: checkSpreadFutures(*sp),
		})
		// reverse
		exp = append(exp, expandedSpread{
			S:         sp,
			Dir:       "reverse",
			Primary:   takeSecondReverse(*sp, "reverse"),
			Secondary: checkSpreadFuturesReverse(*sp),
		})
	}

	// BySpread
	bySpread := make([]expandedSpread, len(exp))
	copy(bySpread, exp)
	sort.SliceStable(bySpread, func(i, j int) bool {
		if bySpread[i].Primary == bySpread[j].Primary {
			return bySpread[i].Secondary > bySpread[j].Secondary
		}
		return bySpread[i].Primary > bySpread[j].Primary
	})

	// ByCourse
	byCourse := make([]expandedSpread, len(exp))
	for k := range exp {
		e := exp[k]
		if e.Dir == "normal" {
			e.Primary = checkSpreadFutures(*e.S)
			e.Secondary = takeSecondReverse(*e.S, "normal")
		} else {
			e.Primary = checkSpreadFuturesReverse(*e.S)
			e.Secondary = takeSecondReverse(*e.S, "reverse")
		}
		byCourse[k] = e
	}
	sort.SliceStable(byCourse, func(i, j int) bool {
		if byCourse[i].Primary == byCourse[j].Primary {
			return byCourse[i].Secondary > byCourse[j].Secondary
		}
		return byCourse[i].Primary > byCourse[j].Primary
	})

	// commit atomically: store spreads slice then expanded view
	cacheMu.Lock()
	cacheSpreads = sps
	cacheSpreadsTime = time.Now()
	cacheMu.Unlock()

	cacheSpreadsAtomic.Store(sps)
	cacheSpreadsExpanded.Store(&TwoSortedSpreadsExpanded{
		BySpread: bySpread,
		ByCourse: byCourse,
	})

	// Rebuild top-funding from pre-cached expanded data
	buildTopFunding()

	log.Printf("reload FUTURES: loaded %d spreads", len(sps))
	return nil
}

// reloadSpotsFromRedis loads "SpotFutures:all" and builds expanded spot views.
func reloadSpotsFromRedis() error {
	reloadSpotsMu.Lock()
	defer reloadSpotsMu.Unlock()

	client := ensureRedisByIndex(1)
	if client == nil {
		return fmt.Errorf("redis client db1 nil")
	}
	raw, err := client.Get(ctx, "SpotFutures:all").Bytes()
	if err != nil {
		return fmt.Errorf("get SpotFutures:all: %w", err)
	}
	var sfs []SpotFuture
	if err := jsonFast.Unmarshal(raw, &sfs); err != nil {
		return fmt.Errorf("unmarshal spots: %w", err)
	}

	// build expanded spots
	expSpots := make([]expandedSpot, 0, len(sfs))
	for i := range sfs {
		sf := &sfs[i]
		course := 0.0
		if sf.Spot1Ask > 0 && sf.Market2Bid > 0 {
			course = ((sf.Market2Bid / sf.Spot1Ask) - 1) * 100
		}
		expSpots = append(expSpots, expandedSpot{S: sf, Primary: sf.Spread, Secondary: course})
	}

	// BySpread
	bySSpread := make([]expandedSpot, len(expSpots))
	copy(bySSpread, expSpots)
	sort.SliceStable(bySSpread, func(i, j int) bool {
		if bySSpread[i].Primary == bySSpread[j].Primary {
			return bySSpread[i].Secondary > bySSpread[j].Secondary
		}
		return bySSpread[i].Primary > bySSpread[j].Primary
	})

	// ByCourse
	bySCourse := make([]expandedSpot, len(expSpots))
	for k := range expSpots {
		e := expSpots[k]
		course := e.Secondary
		bySCourse[k] = expandedSpot{S: e.S, Primary: course, Secondary: e.Primary}
	}
	sort.SliceStable(bySCourse, func(i, j int) bool {
		if bySCourse[i].Primary == bySCourse[j].Primary {
			return bySCourse[i].Secondary > bySCourse[j].Secondary
		}
		return bySCourse[i].Primary > bySCourse[j].Primary
	})

	// commit atomically
	cacheMu.Lock()
	cacheSpots = sfs
	cacheSpotsTime = time.Now()
	cacheMu.Unlock()

	cacheSpotsAtomic.Store(sfs)
	cacheSpotsExpanded.Store(&TwoSortedSpots{
		BySpread: bySSpread,
		ByCourse: bySCourse,
	})

	// Rebuild top-funding-spot from pre-cached expanded data
	buildTopFundingSpot()

	log.Printf("reload SpotsFutures: loaded %d spots", len(sfs))
	return nil
}

// reloadDexFromRedis loads "Dex:all" and builds pre-sorted DEX views.
func reloadDexFromRedis() error {
	reloadDexMu.Lock()
	defer reloadDexMu.Unlock()

	client := ensureRedisByIndex(2)
	if client == nil {
		return fmt.Errorf("redis client db2 nil")
	}
	raw, err := client.Get(ctx, "Dex:all").Bytes()
	if err != nil {
		return fmt.Errorf("get Dex:all: %w", err)
	}
	var dx []Dex
	if err := jsonFast.Unmarshal(raw, &dx); err != nil {
		return fmt.Errorf("unmarshal dex: %w", err)
	}

	// Build pre-sorted views (same pattern as reloadSpreadsFromRedis)
	byFunding := make([]dexEntry, len(dx))
	byDiff := make([]dexEntry, len(dx))
	for i, d := range dx {
		byFunding[i] = dexEntry{d: d, primary: d.FundingRate, secondary: d.Diff}
		byDiff[i] = dexEntry{d: d, primary: d.Diff, secondary: d.FundingRate}
	}

	sort.SliceStable(byFunding, func(i, j int) bool {
		if byFunding[i].primary == byFunding[j].primary {
			return byFunding[i].secondary > byFunding[j].secondary
		}
		return byFunding[i].primary > byFunding[j].primary
	})

	sort.SliceStable(byDiff, func(i, j int) bool {
		if byDiff[i].primary == byDiff[j].primary {
			return byDiff[i].secondary > byDiff[j].secondary
		}
		return byDiff[i].primary > byDiff[j].primary
	})

	cacheMu.Lock()
	cacheDex = dx
	cacheDexTime = time.Now()
	cacheMu.Unlock()

	cacheDexAtomic.Store(dx)
	cacheDexExpanded.Store(&TwoSortedDex{
		ByFunding: byFunding,
		ByDiff:    byDiff,
	})
	log.Printf("reload Dex: loaded %d dex pairs", len(dx))
	return nil
}

// reloadBAContracts loads BinanceAlpha contracts from Redis DB2.
func reloadBAContracts() error {
	client := ensureRedisByIndex(0)
	if client == nil {
		return nil
	}
	raw, err := client.Get(ctx, "BinanceAlpha:contracts").Bytes()
	if err != nil {
		if err == redis.Nil {
			return nil
		}
		return err
	}
	var contracts map[string]map[string]string
	if err := jsonFast.Unmarshal(raw, &contracts); err != nil {
		return err
	}
	cacheMu.Lock()
	cacheBAContracts = contracts
	cacheBAContractsTime = time.Now()
	cacheMu.Unlock()
	return nil
}

// getBACached returns cached contracts (safe for concurrent use).
func getBACached() map[string]map[string]string {
	cacheMu.RLock()
	defer cacheMu.RUnlock()
	return cacheBAContracts
}

// reloadUsersFromDB loads users from MySQL and stores them atomically.
// Call this less frequently (we debounce when reacting to multiple updates).
func reloadUsersFromDB() error {
	reloadUsersMu.Lock()
	defer reloadUsersMu.Unlock()

	us, err := loadUsers()
	if err != nil {
		return fmt.Errorf("loadUsers: %w", err)
	}
	cacheMu.Lock()
	cacheUsers = us
	cacheUsersTime = time.Now()
	cacheMu.Unlock()

	cacheUsersAtomic.Store(us)
	log.Printf("reload Users: loaded %d users", len(us))
	return nil
}

// backgroundCacher refreshes caches every cacheInterval seconds
func backgroundCacher(ctx context.Context, interval time.Duration) {
	ticker := time.NewTicker(interval)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			start := time.Now()
			var wg sync.WaitGroup
			var sps []Spread
			var sfs []SpotFuture
			var dx []Dex
			var us []User
			var errSp, errSpots, errDex, errUsers error

			wg.Add(4)
			go func() {
				defer wg.Done()
				client := ensureRedisByIndex(0)
				if client != nil {
					sps, errSp = loadRedisKeyFromClient[Spread](client, "Spreads:all")
				} else {
					errSp = fmt.Errorf("rdb0 nil")
				}
			}()
			go func() {
				defer wg.Done()
				client := ensureRedisByIndex(1)
				if client != nil {
					sfs, errSpots = loadRedisKeyFromClient[SpotFuture](client, "SpotFutures:all")
				} else {
					errSpots = fmt.Errorf("rdb1 nil")
				}
			}()
			go func() {
				defer wg.Done()
				client := ensureRedisByIndex(2)
				if client != nil {
					dx, errDex = loadRedisKeyFromClient[Dex](client, "Dex:all")
				} else {
					errDex = fmt.Errorf("rdb2 nil")
				}
			}()
			go func() {
				defer wg.Done()
				us, errUsers = loadUsers()
			}()
			go func() {
				defer wg.Done()
				_ = reloadBAContracts()
			}()
			wg.Wait()

			cacheMu.Lock()
            if errSp == nil {
                cacheSpreads = sps
                cacheSpreadsTime = time.Now()
                // store atomically for lock-free readers
                cacheSpreadsAtomic.Store(sps)
            } else {
                log.Printf("cacher: spreads load error: %v", errSp)
            }
            if errSpots == nil {
                cacheSpots = sfs
                cacheSpotsTime = time.Now()
                cacheSpotsAtomic.Store(sfs)
            } else {
                log.Printf("cacher: spots load error: %v", errSpots)
            }
            if errDex == nil {
                cacheDex = dx
                cacheDexTime = time.Now()
                cacheDexAtomic.Store(dx)
            } else {
                log.Printf("cacher: dex load error: %v", errDex)
            }
            if errUsers == nil {
                cacheUsers = us
                cacheUsersTime = time.Now()
            } else {
                log.Printf("cacher: users load error: %v", errUsers)
            }
            cacheMu.Unlock()


            // build expanded entries (pointers into sps)
            exp := make([]expandedSpread, 0, len(sps)*2)
            for i := range sps {
                sp := &sps[i]
                // normal
                exp = append(exp, expandedSpread{
                    S: sp,
                    Dir: "normal",
                    Primary: takeSecondReverse(*sp, "normal"),
                    Secondary: checkSpreadFutures(*sp),
                })
                // reverse
                exp = append(exp, expandedSpread{
                    S: sp,
                    Dir: "reverse",
                    Primary: takeSecondReverse(*sp, "reverse"),
                    Secondary: checkSpreadFuturesReverse(*sp),
                })
            }

            // create copy for BySpread (sort by Primary desc, tie Secondary desc)
            bySpread := make([]expandedSpread, len(exp))
            copy(bySpread, exp)
            sort.SliceStable(bySpread, func(i, j int) bool {
                if bySpread[i].Primary == bySpread[j].Primary {
                    return bySpread[i].Secondary > bySpread[j].Secondary
                }
                return bySpread[i].Primary > bySpread[j].Primary
            })

            // create copy for ByCourse (Primary = entry metric)
            // but for course-view we must recompute Primary as entry metric — safer to fill explicitly:
            byCourse := make([]expandedSpread, len(exp))
            for k := range exp {
                e := exp[k] // copy
                if e.Dir == "normal" {
                    e.Primary = checkSpreadFutures(*e.S)
                    e.Secondary = takeSecondReverse(*e.S, "normal")
                } else {
                    e.Primary = checkSpreadFuturesReverse(*e.S)
                    e.Secondary = takeSecondReverse(*e.S, "reverse")
                }
                byCourse[k] = e
            }
            sort.SliceStable(byCourse, func(i, j int) bool {
                if byCourse[i].Primary == byCourse[j].Primary {
                    return byCourse[i].Secondary > byCourse[j].Secondary
                }
                return byCourse[i].Primary > byCourse[j].Primary
            })

            cacheSpreadsExpanded.Store(&TwoSortedSpreadsExpanded{
                BySpread: bySpread,
                ByCourse: byCourse,
            })

            // Rebuild top-funding from pre-cached expanded data
            buildTopFunding()


            // build expanded spots (pointers into sfs)
            // compute both course and spread, then create two sorted views
            expSpots := make([]expandedSpot, 0, len(sfs))
            for i := range sfs {
                sf := &sfs[i]
                course := 0.0
                if sf.Spot1Ask > 0 && sf.Market2Bid > 0 {
                    course = ((sf.Market2Bid / sf.Spot1Ask) - 1) * 100
                }
                // Primary default fill with Spread; we'll make copies for both views
                expSpots = append(expSpots, expandedSpot{S: sf, Primary: sf.Spread, Secondary: course})
            }

            // BySpread: primary = Spread (desc), tie = course
            bySSpread := make([]expandedSpot, len(expSpots))
            copy(bySSpread, expSpots)
            sort.SliceStable(bySSpread, func(i, j int) bool {
                if bySSpread[i].Primary == bySSpread[j].Primary {
                    return bySSpread[i].Secondary > bySSpread[j].Secondary
                }
                return bySSpread[i].Primary > bySSpread[j].Primary
            })

            // ByCourse: recompute primary = course, tie = spread
            bySCourse := make([]expandedSpot, len(expSpots))
            for k := range expSpots {
                e := expSpots[k]
                // compute course if not present in Secondary
                course := e.Secondary
                // tie-breaker = e.Primary (spread)
                bySCourse[k] = expandedSpot{S: e.S, Primary: course, Secondary: e.Primary}
            }
            sort.SliceStable(bySCourse, func(i, j int) bool {
                if bySCourse[i].Primary == bySCourse[j].Primary {
                    return bySCourse[i].Secondary > bySCourse[j].Secondary
                }
                return bySCourse[i].Primary > bySCourse[j].Primary
            })

            cacheSpotsExpanded.Store(&TwoSortedSpots{
                BySpread: bySSpread,
                ByCourse: bySCourse,
            })

            // Rebuild top-funding-spot from pre-cached expanded data
            buildTopFundingSpot()

            // build DEX pre-sorted views (same pattern as spreads/spots)
            if errDex == nil {
                byFunding := make([]dexEntry, len(dx))
                byDiff := make([]dexEntry, len(dx))
                for i, d := range dx {
                    byFunding[i] = dexEntry{d: d, primary: d.FundingRate, secondary: d.Diff}
                    byDiff[i] = dexEntry{d: d, primary: d.Diff, secondary: d.FundingRate}
                }
                sort.SliceStable(byFunding, func(i, j int) bool {
                    if byFunding[i].primary == byFunding[j].primary {
                        return byFunding[i].secondary > byFunding[j].secondary
                    }
                    return byFunding[i].primary > byFunding[j].primary
                })
                sort.SliceStable(byDiff, func(i, j int) bool {
                    if byDiff[i].primary == byDiff[j].primary {
                        return byDiff[i].secondary > byDiff[j].secondary
                    }
                    return byDiff[i].primary > byDiff[j].primary
                })
                cacheDexExpanded.Store(&TwoSortedDex{
                    ByFunding: byFunding,
                    ByDiff:    byDiff,
                })
            }


			elapsed := time.Since(start)
			log.Printf("cacher: refreshed caches in %.2f ms (spreads=%d spots=%d dex=%d users=%d)",
				float64(elapsed.Milliseconds()), len(sps), len(sfs), len(dx), len(us))
		}
	}
}

// ------------------- CACHE ACCESSORS (only read from cache) -------------------

func getCachedSpreadsExpandedBySpread() []expandedSpread {
    v := cacheSpreadsExpanded.Load()
    if v == nil {
        return nil
    }
    ts := v.(*TwoSortedSpreadsExpanded)
    if ts == nil || ts.BySpread == nil {
        return nil
    }
    out := ts.BySpread
    return out[:len(out):len(out)]
}

func getCachedSpreadsExpandedByCourse() []expandedSpread {
    v := cacheSpreadsExpanded.Load()
    if v == nil {
        return nil
    }
    ts := v.(*TwoSortedSpreadsExpanded)
    if ts == nil || ts.ByCourse == nil {
        return nil
    }
    out := ts.ByCourse
    return out[:len(out):len(out)]
}

func getCachedSpotsExpandedBySpread() []expandedSpot {
    v := cacheSpotsExpanded.Load()
    if v == nil {
        return nil
    }
    ts := v.(*TwoSortedSpots)
    if ts == nil || ts.BySpread == nil {
        return nil
    }
    out := ts.BySpread
    return out[:len(out):len(out)]
}

func getCachedSpotsExpandedByCourse() []expandedSpot {
    v := cacheSpotsExpanded.Load()
    if v == nil {
        return nil
    }
    ts := v.(*TwoSortedSpots)
    if ts == nil || ts.ByCourse == nil {
        return nil
    }
    out := ts.ByCourse
    return out[:len(out):len(out)]
}

func getCachedDexExpandedByFunding() []dexEntry {
    v := cacheDexExpanded.Load()
    if v == nil {
        return nil
    }
    ts := v.(*TwoSortedDex)
    if ts == nil || ts.ByFunding == nil {
        return nil
    }
    out := ts.ByFunding
    return out[:len(out):len(out)]
}

func getCachedDexExpandedByDiff() []dexEntry {
    v := cacheDexExpanded.Load()
    if v == nil {
        return nil
    }
    ts := v.(*TwoSortedDex)
    if ts == nil || ts.ByDiff == nil {
        return nil
    }
    out := ts.ByDiff
    return out[:len(out):len(out)]
}


func getCachedSpreads() []Spread {
    v := cacheSpreadsAtomic.Load()
    if v == nil {
        return nil
    }
    out := v.([]Spread)
    // return slice header copy so callers cannot accidentally append into backing array
    return out[:len(out):len(out)]
}

func getCachedSpots() []SpotFuture {
    v := cacheSpotsAtomic.Load()
    if v == nil {
        return nil
    }
    out := v.([]SpotFuture)
    return out[:len(out):len(out)]
}

func getCachedDex() []Dex {
    v := cacheDexAtomic.Load()
    if v == nil {
        return nil
    }
    out := v.([]Dex)
    return out[:len(out):len(out)]
}

func getCachedUsers() []User {
	v := cacheUsersAtomic.Load()
	if v == nil {
		return nil
	}
	arr := v.([]User)
	// return copy so callers can take addresses / modify safely
	out := make([]User, len(arr))
	copy(out, arr)
	return out
}

// getCachedTopFunding returns cached top-funding futures results
func getCachedTopFunding() []coinFundingResult {
	v := cacheTopFundingAtomic.Load()
	if v == nil {
		return nil
	}
	return v.([]coinFundingResult)
}

// getCachedTopFundingSpot returns cached top-funding spot results
func getCachedTopFundingSpot() []coinFundingSpotResult {
	v := cacheTopFundingSpotAtomic.Load()
	if v == nil {
		return nil
	}
	return v.([]coinFundingSpotResult)
}

// buildTopFunding builds top-16 futures coins from pre-cached pre-sorted expanded spreads.
// Called on every reload from reloadSpreadsFromRedis.
func buildTopFunding() {
	// Use BySpread view — already sorted by funding diff (takeSecondReverse) descending
	exp := getCachedSpreadsExpandedBySpread()
	if exp == nil {
		return
	}

	seen := map[string]struct{}{}
	coins := make([]coinFundingResult, 0, 16)

	for _, e := range exp {
		if e.S == nil {
			continue
		}
		s := e.S

		// Skip already seen symbols (first occurrence wins — highest funding diff)
		if _, ok := seen[s.Symbol]; ok {
			continue
		}
		seen[s.Symbol] = struct{}{}

		// Market1 = lower funding (long side), Market2 = higher funding (short side)
		m1, m2 := s.Market1, s.Market2
		f1, f2 := s.Market1Funding, s.Market2Funding
		if f1 > f2 {
			m1, m2 = s.Market2, s.Market1
			f1, f2 = s.Market2Funding, s.Market1Funding
		}

		fundingDiff := f2 - f1
		entry := checkSpreadFutures(*s)

		coins = append(coins, coinFundingResult{
			Symbol:   s.Symbol,
			Market1:  m1,
			Market2:  m2,
			Funding1: f1,
			Funding2: f2,
			Spread:   fundingDiff,
			Entry:    entry,
		})

		if len(coins) >= 16 {
			break
		}
	}

	cacheTopFundingAtomic.Store(coins)
}

// buildTopFundingSpot builds top-16 spot/futures coins from pre-cached raw spot data.
// Uses same data source as handleSpotPages (getCachedSpots), no user-specific filtering.
func buildTopFundingSpot() {
	// Use BySpread view — already sorted by Spread (funding rate) descending
	exp := getCachedSpotsExpandedBySpread()
	if exp == nil {
		return
	}

	seen := map[string]struct{}{}
	coins := make([]coinFundingSpotResult, 0, 16)

	for _, e := range exp {
		if e.S == nil {
			continue
		}
		sf := e.S

		// Skip zero/negative funding
		if sf.Spread <= 0 {
			continue
		}

		// Dedup by symbol — first wins (already sorted by funding desc)
		if _, ok := seen[sf.Symbol]; ok {
			continue
		}
		seen[sf.Symbol] = struct{}{}

		entry := 0.0
		if sf.Spot1Ask > 0 && sf.Market2Bid > 0 {
			entry = ((sf.Market2Bid / sf.Spot1Ask) - 1) * 100
		}

		coins = append(coins, coinFundingSpotResult{
			Symbol:   sf.Symbol,
			Market1:  sf.Market1,
			Market2:  sf.Market2,
			Funding2: sf.Spread,
			Spread:   sf.Spread,
			Entry:    entry,
		})

		if len(coins) >= 16 {
			break
		}
	}

	cacheTopFundingSpotAtomic.Store(coins)
}

// ------------------- API HANDLERS (use cache only) -------------------

// /api/futures?user_id=123&page=0&items=5
func handleFutures(w http.ResponseWriter, r *http.Request) {
	userID := r.URL.Query().Get("user_id")
	pageStr := r.URL.Query().Get("page")
	itemsStr := r.URL.Query().Get("items")
	page := 0
	if pageStr != "" {
		p, _ := strconv.Atoi(pageStr)
		page = p
	}
	currentPage := page
	if currentPage < 1 {
		currentPage = 1
	}
	items := 5
	if itemsStr != "" {
		if it, err := strconv.Atoi(itemsStr); err == nil && it >= 1 {
			items = it
			if items > 200 {
				items = 200
			}
		}
	}

	// parse overrides from GET
	sortParam := r.URL.Query().Get("sort")        // "funding" or "spread"
	ltParam := r.URL.Query().Get("lt")           // "1" or "0"
	listFutures := r.URL.Query().Get("listfutures") // comma list "1,0,1,..."

	dsStr, dsPresent := buildDataSearchFromParams(sortParam, ltParam)

	var marketsOverride map[string]int
	if strings.TrimSpace(listFutures) != "" {
		marketsOverride = parseListMarketsParam(listFutures)
	}

	spreads := getCachedSpreads()
	accounts := getCachedUsers()

	var dsptr *string
	if dsPresent {
		dsptr = &dsStr
	}
	inlines, _, active := getUserSpreads(spreads, accounts, userID, dsptr, marketsOverride)
	if !active {
		jsonResponse(w, map[string]interface{}{"status": "no_sub"})
		return
	}
	if len(inlines) == 0 {
		jsonResponse(w, map[string]interface{}{"status": "reloading"})
		return
	}
	resp := paginateSpreads(inlines, currentPage, items, 20)
	jsonResponse(w, resp)
}


// /api/spot?user_id=123&page=0&items=5
func handleSpot(w http.ResponseWriter, r *http.Request) {
	userID := r.URL.Query().Get("user_id")
	pageStr := r.URL.Query().Get("page")
	itemsStr := r.URL.Query().Get("items")
	page := 0
	if pageStr != "" {
		p, _ := strconv.Atoi(pageStr)
		page = p
	}
	currentPage := page
	if currentPage < 1 {
		currentPage = 1
	}
	items := 5
	if itemsStr != "" {
		if it, err := strconv.Atoi(itemsStr); err == nil && it >= 1 {
			items = it
			if items > 200 {
				items = 200
			}
		}
	}

	// parse overrides
	sortParam := r.URL.Query().Get("sort")
	ltParam := r.URL.Query().Get("lt")
	listSpot := r.URL.Query().Get("listspot")

	dsStr, dsPresent := buildDataSearchFromParams(sortParam, ltParam)
	var marketsOverride map[string]int
	if strings.TrimSpace(listSpot) != "" {
		marketsOverride = parseListMarketsParam(listSpot)
	}

	spots := getCachedSpots()
	accounts := getCachedUsers()

	var dsptr *string
	if dsPresent {
		dsptr = &dsStr
	}
	inlines, _, active := getUserSpots(spots, accounts, userID, dsptr, marketsOverride)
	if !active {
		jsonResponse(w, map[string]interface{}{"status": "no_sub"})
		return
	}
	if len(inlines) == 0 {
		jsonResponse(w, map[string]interface{}{"status": "reloading"})
		return
	}
	resp := paginateSpreads(inlines, currentPage, items, 20)
	jsonResponse(w, resp)
}


// /api/futures_pages?user_id=...&symbol=ETHUSDT&items=5  (handler)
func handleFuturesPages(w http.ResponseWriter, r *http.Request) {
	userID := r.URL.Query().Get("user_id")
	symbol := r.URL.Query().Get("symbol")
	if symbol == "" {
		symbol = "ETHUSDT"
	}
	itemsStr := r.URL.Query().Get("items")
	items := 5
	if itemsStr != "" {
		if it, err := strconv.Atoi(itemsStr); err == nil && it > 0 {
			items = it
		}
	}

	accounts := getCachedUsers()

	spreadsSym := fetchSpreadsSymbolCached(getCachedSpreads(), symbol)
	if len(spreadsSym) == 0 {
		jsonResponse(w, map[string]interface{}{"status": "empty"})
		return
	}

	// find user's account and check active
	var userAcc *User
    for i := range accounts {
        if accounts[i].Tgid == userID {
            userAcc = &accounts[i]
            break
        }
    }
	if userAcc == nil {
		jsonResponse(w, map[string]interface{}{"status": "no_sub"})
		return
	}

		// parse overrides if present
	sortParam := r.URL.Query().Get("sort")
	ltParam := r.URL.Query().Get("lt")
	listFutures := r.URL.Query().Get("listfutures")

	dsStr, dsPresent := buildDataSearchFromParams(sortParam, ltParam)

	marketsFutures := userAcc.ListMarketsFutures
	if strings.TrimSpace(listFutures) != "" {
		marketsFutures = parseListMarketsParam(listFutures)
	}

	dataSearchRaw := ""
	if dsPresent {
		dataSearchRaw = dsStr
	} else {
		dataSearchRaw, _ = jsonFast.MarshalToString(userAcc.DataSearch)
	}

	blackset := userAcc.Blacklist

	// Use filterSpreadsForPages -> returns []interface{} of []string{label,id}
	msgs := filterSpreadsForPages(spreadsSym, marketsFutures, dataSearchRaw, blackset)
	if len(msgs) == 0 {
		jsonResponse(w, map[string]interface{}{"status": "empty"})
		return
	}

	resp := paginateAllSpreads(msgs, items)
	response := map[string]interface{}{
		"status": "active",
		"symbol": symbol,
	}
	for k, v := range resp {
		response[k] = v
	}
	jsonResponse(w, response)
}

func handleSpotPages(w http.ResponseWriter, r *http.Request) {
	userID := r.URL.Query().Get("user_id")
	symbol := r.URL.Query().Get("symbol")
	if symbol == "" {
		symbol = "ETHUSDT"
	}
	itemsStr := r.URL.Query().Get("items")
	items := 5
	if itemsStr != "" {
		if it, err := strconv.Atoi(itemsStr); err == nil && it > 0 {
			items = it
		}
	}

	users := getCachedUsers()

	// find user
	var user *User
	for i := range users {
		if users[i].Tgid == userID {
			user = &users[i]
			break
		}
	}
	if user == nil {
		jsonResponse(w, map[string]interface{}{"status": "no_sub"})
		return
	}

	spotsSym := fetchSpotSpreadsSymbolCached(getCachedSpots(), symbol)
	if len(spotsSym) == 0 {
		jsonResponse(w, map[string]interface{}{"status": "empty"})
		return
	}

	// parse overrides
	sortParam := r.URL.Query().Get("sort")
	ltParam := r.URL.Query().Get("lt")
	listSpot := r.URL.Query().Get("listspot")

	dsStr, dsPresent := buildDataSearchFromParams(sortParam, ltParam)

	marketsSpot := user.ListMarketsSpot
	if strings.TrimSpace(listSpot) != "" {
		marketsSpot = parseListMarketsParam(listSpot)
	}
	dataSearchRaw := ""
	if dsPresent {
		dataSearchRaw = dsStr
	} else {
		dataSearchRaw, _ = jsonFast.MarshalToString(user.DataSearch)
	}

	blackset := user.Blacklist

	msgs := filterSpotsForPages(spotsSym, marketsSpot, dataSearchRaw, blackset)
	if len(msgs) == 0 {
		jsonResponse(w, map[string]interface{}{"status": "empty"})
		return
	}
	resp := paginateAllSpreads(msgs, items)
	response := map[string]interface{}{
		"status": "active",
		"symbol": symbol,
	}
	for k, v := range resp {
		response[k] = v
	}
	jsonResponse(w, response)
}

func handleFuturesID(w http.ResponseWriter, r *http.Request) {
	userID := r.URL.Query().Get("user_id")
	findSymbol := r.URL.Query().Get("symbol")
	if findSymbol == "" {
		findSymbol = "ETH"
	}
	findM1 := r.URL.Query().Get("m1")
	findM2 := r.URL.Query().Get("m2")

	users := getCachedUsers()
	// check active
	active := false
	for _, acc := range users {
		if acc.Tgid == userID {
			if (acc.IsActive == "1" && acc.IsActiveAdmin == "2") || acc.IsActiveAdmin == "1" || acc.TestActive == "1" {
				active = true
			}
			break
		}
	}
	if !active {
		jsonResponse(w, map[string]interface{}{"status": "no_sub"})
		return
	}
	spread := getSpreadBySymbolAndMarketsCachedOptimized(getCachedSpreads(), findSymbol, findM1, findM2)
	if spread == nil {
		jsonResponse(w, map[string]interface{}{"status": "empty"})
		return
	}
	msg := createMessageToFutures(*spread, findM1)
	jsonResponse(w, map[string]interface{}{"status": "ok", "data": msg})
}

func handleSpotID(w http.ResponseWriter, r *http.Request) {
	userID := r.URL.Query().Get("user_id")
	findSymbol := r.URL.Query().Get("symbol")
	if findSymbol == "" {
		findSymbol = "ETH"
	}
	findM1 := r.URL.Query().Get("m1")
	findM2 := r.URL.Query().Get("m2")

	users := getCachedUsers()
	active := false
	for _, acc := range users {
		if acc.Tgid == userID {
			if (acc.IsActive == "1" && acc.IsActiveAdmin == "2") || acc.IsActiveAdmin == "1" || acc.TestActive == "1" {
				active = true
			}
			break
		}
	}
	if !active {
		jsonResponse(w, map[string]interface{}{"status": "no_sub"})
		return
	}
	spread := getSpotSpreadBySymbolAndMarketsCachedOptimized(getCachedSpots(), findSymbol, findM1, findM2)
	if spread == nil {
		jsonResponse(w, map[string]interface{}{"status": "empty"})
		return
	}
	msg := createMessageToSpot(*spread)
	jsonResponse(w, map[string]interface{}{"status": "ok", "data": msg})
}

// ------------------- FUNDING BOT LOOP (uses cache only) -------------------

func fundingBotLoop(ctx context.Context, interval time.Duration) {
	ticker := time.NewTicker(interval)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			start := time.Now()
			users := getCachedUsers()
			// filter active and monitoring users for bot
			users = filterActiveUsersBot(users)
			users = filterMonitoringUsers(users)
			spreads := getCachedSpreads()
			spots := getCachedSpots()
			dex := getCachedDex()

			var wg sync.WaitGroup
			for i := range users {
				wg.Add(1)
				u := &users[i]
				go func(u *User) {
					defer wg.Done()
					processUser(u, spreads, spots, dex)
				}(u)
			}
			wg.Wait()
			log.Printf("fundingBot cycle done in %.2f ms (users=%d)", float64(time.Since(start).Milliseconds()), len(users))
		}
	}
}

// ------------------- PROCESSING / HANDLERS (copied logic unchanged) -------------------

// copyLastCoins делает копию map для сравнения/отладки
func copyLastCoins(src map[string]time.Time) map[string]time.Time {
	out := make(map[string]time.Time, len(src))
	for k, v := range src {
		out[k] = v
	}
	return out
}

func floatFromData(v interface{}) float64 {
	switch x := v.(type) {
	case float64:
		return x
	case string:
		f, _ := strconv.ParseFloat(x, 64)
		return f
	default:
		return 0
	}
}

// parseLastCoins: raw is zlib-compressed JSON blob or nil/"no"
func parseLastCoins(raw []byte) map[string]time.Time {
	out := map[string]time.Time{}
	if raw == nil || len(raw) == 0 {
		return out
	}
	if string(raw) == "no" {
		return out
	}
	// Try zlib
	r, err := zlib.NewReader(bytes.NewReader(raw))
	if err != nil {
		// plain JSON?
		var maybe map[string]string
		if err2 := jsonFast.Unmarshal(raw, &maybe); err2 == nil {
			for k, v := range maybe {
				if tm, ok := parseIsoTime(v); ok {
					out[k] = tm
				}
			}
		}
		return out
	}
	defer r.Close()
	var buf bytes.Buffer
	_, _ = buf.ReadFrom(r)
	var m map[string]string
	if err := jsonFast.Unmarshal(buf.Bytes(), &m); err != nil {
		return out
	}
	for k, v := range m {
		if tm, ok := parseIsoTime(v); ok {
			out[k] = tm
		}
	}
	return out
}

func parseIsoTime(s string) (time.Time, bool) {
	if s == "" {
		return time.Time{}, false
	}
	layouts := []string{
		time.RFC3339Nano,
		time.RFC3339,
		"2006-01-02T15:04:05.999999",
		"2006-01-02T15:04:05.999",
		"2006-01-02T15:04:05",
	}
	for _, l := range layouts {
		if t, err := time.Parse(l, s); err == nil {
			return t, true
		}
	}
	if t, err := time.Parse("2006-01-02 15:04:05", strings.ReplaceAll(s, "T", " ")); err == nil {
		return t, true
	}
	return time.Time{}, false
}

func cleanLastCoins(last map[string]time.Time) (map[string]time.Time, []byte) {
	now := time.Now()
	clean := map[string]time.Time{}
	for k, v := range last {
		if now.Sub(v).Seconds() <= FOUR_HOURS_SECONDS {
			clean[k] = v
		}
	}
	// trim by MAX_ENTRIES
	if len(clean) > MAX_ENTRIES {
		type kv struct {
			k string
			t time.Time
		}
		arr := make([]kv, 0, len(clean))
		for k, v := range clean {
			arr = append(arr, kv{k: k, t: v})
		}
		sort.Slice(arr, func(i, j int) bool { return arr[i].t.Before(arr[j].t) })
		for len(clean) > MAX_ENTRIES && len(arr) > 0 {
			old := arr[0]
			delete(clean, old.k)
			arr = arr[1:]
		}
	}
	// compress
	if len(clean) == 0 {
		return map[string]time.Time{}, nil
	}
	strMap := make(map[string]string, len(clean))
	for k, v := range clean {
		strMap[k] = v.Format("2006-01-02T15:04:05.999999")
	}
	rawJson, _ := jsonFast.Marshal(strMap)
	compressed := zlibCompress(rawJson)

	// if too big - remove oldest until ok
	if len(compressed) > MAX_COMPRESSED_SIZE && len(clean) > 0 {
		type kv struct {
			k string
			t time.Time
		}
		arr := make([]kv, 0, len(clean))
		for k, v := range clean {
			arr = append(arr, kv{k: k, t: v})
		}
		sort.Slice(arr, func(i, j int) bool { return arr[i].t.Before(arr[j].t) })
		for len(compressed) > MAX_COMPRESSED_SIZE && len(arr) > 0 {
			old := arr[0]
			delete(clean, old.k)
			arr = arr[1:]
			strMap = make(map[string]string, len(clean))
			for k, v := range clean {
				strMap[k] = v.Format("2006-01-02T15:04:05.999999")
			}
			rawJson, _ = jsonFast.Marshal(strMap)
			compressed = zlibCompress(rawJson)
		}
	}
	return clean, compressed
}

func zlibCompress(b []byte) []byte {
	var buf bytes.Buffer
	w := zlib.NewWriter(&buf)
	_, _ = w.Write(b)
	_ = w.Close()
	return buf.Bytes()
}

func persistLastCoins(tgid string, compressed []byte) error {
	var arg interface{}
	if compressed == nil {
		arg = "no"
	} else {
		arg = compressed
	}
	_, err := db.Exec("UPDATE Users SET lastNoticeCoins = ? WHERE tgid = ?", arg, tgid)
	return err
}

// pushNotificationGeneric: RPUSH payload into Redis list (dbIndex), then LTRIM
func pushNotificationGeneric(dbIndex int, listKey string, payload interface{}) error {
	client := ensureRedisByIndex(dbIndex)
	if client == nil {
		return fmt.Errorf("redis client db%d nil", dbIndex)
	}
	b, err := jsonFast.Marshal(payload)
	if err != nil {
		return fmt.Errorf("marshal payload: %w", err)
	}
	if err := client.RPush(ctx, listKey, b).Err(); err != nil {
		return fmt.Errorf("redis rpush: %w", err)
	}
	start := -int64(NOTIF_LIST_LIMIT)
	if err := client.LTrim(ctx, listKey, start, -1).Err(); err != nil {
		log.Printf("redis ltrim error for %s db%d: %v", listKey, dbIndex, err)
	}

    // mark pending (do NOT publish per-notification)
    atomic.StoreInt32(&notifPending[dbIndex], 1)
	return nil
}

// ------------------- FILTER / BUILD for FUTURES (from original) -------------------

type spreadWithDir struct {
	S   Spread
	Dir string // "normal" or "reverse"
}

func expandSpreadsWithDirections(spreads []Spread) []spreadWithDir {
	out := make([]spreadWithDir, 0, len(spreads)*2)
	for _, s := range spreads {
		out = append(out, spreadWithDir{S: s, Dir: "normal"})
		out = append(out, spreadWithDir{S: s, Dir: "reverse"})
	}
	return out
}

// checkSpreadFutures and checkSpreadFuturesReverse approximations / original logic
func checkSpreadFutures(s Spread) float64 {
	// original logic: return entry / significance metric — we re-use s.Spread as proxy when unknown
	// but keep formula for entry: (market1bid / market2ask - 1) * 100
	if s.Market1Bid == 0 || s.Market2Ask == 0 {
		return s.Spread
	}
	return ((s.Market1Bid / s.Market2Ask) - 1) * 100
}
func checkSpreadFuturesReverse(s Spread) float64 {
	// reverse entry: (market2bid / market1ask - 1) * 100
	if s.Market2Bid == 0 || s.Market1Ask == 0 {
		return s.Spread
	}
	return ((s.Market2Bid / s.Market1Ask) - 1) * 100
}

func checkExitSpreadFutures(s Spread) float64 {
	// original logic: return entry / significance metric — we re-use s.Spread as proxy when unknown
	// but keep formula for entry: (market1bid / market2ask - 1) * 100
	if s.Market1Ask == 0 || s.Market2Bid == 0 {
		return s.Spread
	}
	return ((s.Market1Ask / s.Market2Bid) - 1) * 100
}
func checkExitSpreadFuturesReverse(s Spread) float64 {
	// reverse entry: (market2bid / market1ask - 1) * 100
	if s.Market2Ask == 0 || s.Market1Bid == 0 {
		return s.Spread
	}
	return ((s.Market2Ask / s.Market1Bid) - 1) * 100
}

func takeSecondReverse(s Spread, dir string) float64 {
	// second metric approximated as spread or funding diff depending on dir
	if dir == "normal" {
		return s.Spread
	}
	return s.Market2Funding - s.Market1Funding
}

func buildInlineButtonFutures(s Spread, dir string) []string {
	var val float64
	if dir == "normal" {
		val = checkSpreadFutures(s)
	} else {
		val = checkSpreadFuturesReverse(s)
	}
	return []string{fmt.Sprintf("%s: %.2f вход", s.Symbol, val), s.Symbol}
}

func buildInlineButtonSpot(s Spread, dir string) []string {
	var spreadVal float64
	if dir == "normal" {
		spreadVal = s.Market1Funding - s.Market2Funding
	} else {
		spreadVal = s.Market2Funding - s.Market1Funding
	}
	return []string{fmt.Sprintf("%s: %.2f%% тек", s.Symbol, spreadVal), s.Symbol}
}
// filterSpreads — ускоренная версия с параллельной сортировкой и лимитом активных фильтров
func filterSpreads(spreads []Spread, marketsDict map[string]int, dataSearchRaw string, blacklist map[string]struct{}, active bool) ([]interface{}, map[string]interface{}, bool) {
    // ограничиваем активные фильтры
    spreadWorkPool <- struct{}{}
    defer func() { <-spreadWorkPool }()

    // 1️⃣ Фильтр по маркетам и blacklist
    filtered := make([]Spread, 0, len(spreads))
    for _, s := range spreads {
        if marketsDict[strings.ToUpper(strings.TrimSpace(s.Market1))] == 0 ||
            marketsDict[strings.ToUpper(strings.TrimSpace(s.Market2))] == 0 {
            continue
        }
        if _, ok := blacklist[strings.ToUpper(strings.TrimSpace(s.Symbol))]; ok {
            continue
        }
        filtered = append(filtered, s)
    }

    // 2️⃣ Разбор dataSearch
    var dataSearch map[string]interface{}
    if dataSearchRaw == "" || dataSearchRaw == "no" {
        dataSearch = map[string]interface{}{}
    } else {
        _ = jsonFast.UnmarshalFromString(dataSearchRaw, &dataSearch)
        if dataSearch == nil {
            dataSearch = map[string]interface{}{}
        }
    }

    if len(filtered) == 0 {
        return []interface{}{}, dataSearch, active
    }

    // 3️⃣ Расширяем направления
    exp := expandSpreadsWithDirections(filtered)
    n := len(exp)
    if n == 0 {
        return []interface{}{}, dataSearch, active
    }

    // 4️⃣ Вычисляем метрики параллельно
    type metricItem struct {
        Item      spreadWithDir
        Primary   float64
        Secondary float64
    }
    metrics := make([]metricItem, 0, n)
    results := make(chan metricItem, n)
    workers := int(math.Max(2, float64(runtime.NumCPU()/2)))

    go func() {
        wg := sync.WaitGroup{}
        chunk := make(chan spreadWithDir, workers*4)
        for i := 0; i < workers; i++ {
            wg.Add(1)
            go func() {
                defer wg.Done()
                for it := range chunk {
                    var prim float64
                    if dataSearch["filter_course_or_spread"] == "1" {
                        if it.Dir == "normal" {
                            prim = checkSpreadFutures(it.S)
                        } else {
                            prim = checkSpreadFuturesReverse(it.S)
                        }
                    } else {
                        prim = takeSecondReverse(it.S, it.Dir)
                    }
                    sec := takeSecondReverse(it.S, it.Dir)
                    results <- metricItem{Item: it, Primary: prim, Secondary: sec}
                }
            }()
        }
        for _, it := range exp {
            chunk <- it
        }
        close(chunk)
        wg.Wait()
        close(results)
    }()

    for r := range results {
        metrics = append(metrics, r)
    }

    // 5️⃣ Параллельная сортировка
    chunks := int(math.Min(4, float64(runtime.NumCPU())))
    chunkSize := (len(metrics) + chunks - 1) / chunks
    var sortWg sync.WaitGroup
    for i := 0; i < chunks; i++ {
        start := i * chunkSize
        end := start + chunkSize
        if end > len(metrics) {
            end = len(metrics)
        }
        sortWg.Add(1)
        go func(start, end int) {
            defer sortWg.Done()
            sort.Slice(metrics[start:end], func(i, j int) bool {
                a, b := metrics[start+i], metrics[start+j]
                if a.Primary == b.Primary {
                    return a.Secondary > b.Secondary
                }
                return a.Primary > b.Primary
            })
        }(start, end)
    }
    sortWg.Wait()

    // Финальный merge-pass
    sort.SliceStable(metrics, func(i, j int) bool {
        if metrics[i].Primary == metrics[j].Primary {
            return metrics[i].Secondary > metrics[j].Secondary
        }
        return metrics[i].Primary > metrics[j].Primary
    })

    // 6️⃣ Дедуп и построение inline-кнопок
    seen := map[string]struct{}{}
    inlines := make([]interface{}, 0, len(metrics))
    for _, mi := range metrics {
        s := mi.Item.S
        dir := mi.Item.Dir
        if _, ok := seen[s.Symbol]; ok {
            continue
        }
        seen[s.Symbol] = struct{}{}

        if dataSearch["filter_course_or_spread"] == "1" {
            if dataSearch["filter_big_or_all_course"] == "1" {
                if dir == "normal" {
                    if checkSpreadFutures(s) <= 0 {
                        continue
                    }
                } else {
                    if checkSpreadFuturesReverse(s) <= 0 {
                        continue
                    }
                }
            }
            inlines = append(inlines, buildInlineButtonFutures(s, dir))
            continue
        }

        if dataSearch["filter_big_or_all_course"] == "1" {
            if dir == "normal" {
                if checkSpreadFutures(s) <= 0 {
                    continue
                }
            } else {
                if checkSpreadFuturesReverse(s) <= 0 {
                    continue
                }
            }
        }
        inlines = append(inlines, buildInlineButtonSpot(s, dir))
    }

    return inlines, dataSearch, active
}

// filterSpreadsExpanded — fast path: принимает уже предсортированный expanded view.
// Сохраняет оригинальную логику фильтрации/dedup, но работает O(N) по предсортированному массиву.
func filterSpreadsExpanded(exp []expandedSpread, marketsDict map[string]int, dataSearchRaw string, blacklist map[string]struct{}, active bool) ([]interface{}, map[string]interface{}, bool) {
	// same concurrency limiter as original
	spreadWorkPool <- struct{}{}
	defer func() { <-spreadWorkPool }()

	// parse dataSearch
	var dataSearch map[string]interface{}
	if dataSearchRaw == "" || dataSearchRaw == "no" {
		dataSearch = map[string]interface{}{}
	} else {
		_ = jsonFast.UnmarshalFromString(dataSearchRaw, &dataSearch)
		if dataSearch == nil {
			dataSearch = map[string]interface{}{}
		}
	}

	if len(exp) == 0 {
		return []interface{}{}, dataSearch, active
	}

	seen := map[string]struct{}{}
	inlines := make([]interface{}, 0, len(exp))

	for _, e := range exp {
		// note: e.S is pointer to original Spread (safe because backgroundCacher stores original slice)
		if e.S == nil {
			continue
		}
		s := e.S

		// markets availability check (same as original)
		if marketsDict[strings.ToUpper(strings.TrimSpace(s.Market1))] == 0 ||
			marketsDict[strings.ToUpper(strings.TrimSpace(s.Market2))] == 0 {
			continue
		}
		// blacklist
		if _, ok := blacklist[strings.ToUpper(strings.TrimSpace(s.Symbol))]; ok {
			continue
		}

		// dedupe by symbol — **same behavior** as original: first occurrence wins
		if _, ok := seen[s.Symbol]; ok {
			continue
		}
		seen[s.Symbol] = struct{}{}

		// now apply filters and build inline buttons preserving original logic
		if dataSearch["filter_course_or_spread"] == "1" {
			// course-mode
			if dataSearch["filter_big_or_all_course"] == "1" {
				// original logic: check entry metric (different for normal/reverse)
				if e.Dir == "normal" {
					if checkSpreadFutures(*s) <= 0 {
						continue
					}
				} else {
					if checkSpreadFuturesReverse(*s) <= 0 {
						continue
					}
				}
			}
			// build futures inline button
			inlines = append(inlines, buildInlineButtonFutures(*s, e.Dir))
			continue
		}

		// default (spot-like) branch: original used checkSpreadFutures as approximation for "big only"
		if dataSearch["filter_big_or_all_course"] == "1" {
			if checkSpreadFutures(*s) <= 0 {
				continue
			}
		}
		inlines = append(inlines, buildInlineButtonSpot(*s, e.Dir))
	}

	return inlines, dataSearch, active
}


// getUserSpreads finds user in provided accounts (parsed) and runs filterSpreads or fast filterSpreadsExpanded
// Added marketsOverride: if non-nil and non-empty, we use it instead of acc.ListMarketsFutures.
// dataSearchParam behavior unchanged: if non-nil we parse it and replace acc.DataSearch for this call.
func getUserSpreads(spreads []Spread, accounts []User, tgid string, dataSearchParam *string, marketsOverride map[string]int) ([]interface{}, map[string]interface{}, bool) {
	active := false
	for _, acc := range accounts {
		if acc.Tgid == tgid {
			if (acc.IsActive == "1" && acc.IsActiveAdmin == "2") || acc.IsActiveAdmin == "1" || acc.TestActive == "1" {
				active = true
			} else {
				return []interface{}{}, map[string]interface{}{}, false
			}

			// markets: prefer override if provided, else user's saved markets
			marketsFutures := acc.ListMarketsFutures
			if marketsOverride != nil && len(marketsOverride) > 0 {
				marketsFutures = marketsOverride
			}

			// dataSearch: replace entirely if param provided (as requested)
			dataSearch := acc.DataSearch
			if dataSearchParam != nil {
				ds := parseJSONMap(*dataSearchParam)
				if len(ds) > 0 {
					dataSearch = ds
				}
			}

			blackset := acc.Blacklist
			dsRaw, _ := jsonFast.MarshalToString(dataSearch)

			// choose expanded pre-sorted view if available (respecting dataSearch)
			filterCourse := false
			if v, ok := dataSearch["filter_course_or_spread"]; ok {
				switch t := v.(type) {
				case string:
					if strings.TrimSpace(t) == "1" {
						filterCourse = true
					}
				case float64:
					if int(t) == 1 {
						filterCourse = true
					}
				}
			}

			if filterCourse {
				exp := getCachedSpreadsExpandedByCourse()
				if exp != nil && len(exp) > 0 {
					inlines, ds, act := filterSpreadsExpanded(exp, marketsFutures, string(dsRaw), blackset, active)
					return inlines, ds, act
				}
			} else {
				exp := getCachedSpreadsExpandedBySpread()
				if exp != nil && len(exp) > 0 {
					inlines, ds, act := filterSpreadsExpanded(exp, marketsFutures, string(dsRaw), blackset, active)
					return inlines, ds, act
				}
			}

			// fallback to original (no expanded view yet)
			inlines, ds, act := filterSpreads(spreads, marketsFutures, string(dsRaw), blackset, active)
			return inlines, ds, act
		}
	}
	return []interface{}{}, map[string]interface{}{}, false
}


// ------------------- FILTER / BUILD for SPOT -------------------

func buildInlineButtonSpotFuture(sf SpotFuture, useCourse bool, val float64) []string {
	if useCourse {
		return []string{fmt.Sprintf("%s: %.2f вход", sf.Symbol, val), sf.Symbol}
	}
	return []string{fmt.Sprintf("%s: %.2f%% тек", sf.Symbol, val), sf.Symbol}
}

// filterSpotsExpanded — fast path using pre-sorted expanded spots
func filterSpotsExpanded(exp []expandedSpot, marketsDict map[string]int, dataSearchRaw string, blacklist map[string]struct{}, active bool) ([]interface{}, map[string]interface{}, bool) {
    spotWorkPool <- struct{}{}
    defer func() { <-spotWorkPool }()

    var dataSearch map[string]interface{}
    if dataSearchRaw == "" || dataSearchRaw == "no" {
        dataSearch = map[string]interface{}{}
    } else {
        _ = jsonFast.UnmarshalFromString(dataSearchRaw, &dataSearch)
        if dataSearch == nil {
            dataSearch = map[string]interface{}{}
        }
    }

    if len(exp) == 0 {
        return []interface{}{}, dataSearch, active
    }

    filterCourse := false
    if v, ok := dataSearch["filter_course_or_spread"]; ok {
        switch t := v.(type) {
        case string:
            if strings.TrimSpace(t) == "1" {
                filterCourse = true
            }
        case float64:
            if int(t) == 1 {
                filterCourse = true
            }
        }
    }

    filterBig := false
    if v, ok := dataSearch["filter_big_or_all_course"]; ok {
        switch t := v.(type) {
        case string:
            if strings.TrimSpace(t) == "1" {
                filterBig = true
            }
        case float64:
            if int(t) == 1 {
                filterBig = true
            }
        }
    }

    seen := map[string]struct{}{}
    inlines := make([]interface{}, 0, len(exp))

    for _, e := range exp {
        if e.S == nil {
            continue
        }
        sf := e.S

        if marketsDict[strings.ToUpper(strings.TrimSpace(sf.Market1))] == 0 ||
            marketsDict[strings.ToUpper(strings.TrimSpace(sf.Market2))] == 0 {
            continue
        }
        if _, ok := blacklist[strings.ToUpper(strings.TrimSpace(sf.Symbol))]; ok {
            continue
        }
        if _, ok := seen[sf.Symbol]; ok {
            continue
        }
        seen[sf.Symbol] = struct{}{}

        if filterCourse {
            if filterBig && e.Primary <= 0 {
                continue
            }
            // e.Primary already course for ByCourse view; for BySpread view Primary = spread (but we won't call ByCourse in that case)
            inlines = append(inlines, buildInlineButtonSpotFuture(*sf, true, e.Primary))
        } else {
            if filterBig && e.Primary <= 0 {
                continue
            }
            inlines = append(inlines, buildInlineButtonSpotFuture(*sf, false, e.Primary))
        }
    }

    return inlines, dataSearch, active
}

// filterSpots — ускоренная версия с параллельной сортировкой и лимитом активных фильтров
func filterSpots(spots []SpotFuture, marketsDict map[string]int, dataSearchRaw string, blacklist map[string]struct{}, active bool) ([]interface{}, map[string]interface{}, bool) {
	// Лимит активных фильтров, чтобы не перегружать CPU
	spotWorkPool <- struct{}{}
	defer func() { <-spotWorkPool }()

	recs := metricSpotPool.Get().([]MetricSpot)
	defer func() {
		recs = recs[:0]
		metricSpotPool.Put(recs)
	}()

	// 1️⃣ Фильтр по маркетам и blacklist
	filtered := make([]SpotFuture, 0, len(spots))
	for _, s := range spots {
		if marketsDict[strings.ToUpper(strings.TrimSpace(s.Market1))] == 0 ||
			marketsDict[strings.ToUpper(strings.TrimSpace(s.Market2))] == 0 {
			continue
		}
		if _, ok := blacklist[strings.ToUpper(strings.TrimSpace(s.Symbol))]; ok {
			continue
		}
		filtered = append(filtered, s)
	}
	if len(filtered) == 0 {
		return []interface{}{}, map[string]interface{}{}, active
	}

	// 2️⃣ Разбор dataSearch
	var dataSearch map[string]interface{}
	if dataSearchRaw == "" || dataSearchRaw == "no" {
		dataSearch = map[string]interface{}{}
	} else {
		_ = jsonFast.UnmarshalFromString(dataSearchRaw, &dataSearch)
		if dataSearch == nil {
			dataSearch = map[string]interface{}{}
		}
	}

	// определить режим (вход / фандинг)
	filterCourse := false
	if v, ok := dataSearch["filter_course_or_spread"]; ok {
		switch t := v.(type) {
		case string:
			if strings.TrimSpace(t) == "1" {
				filterCourse = true
			}
		case float64:
			if int(t) == 1 {
				filterCourse = true
			}
		}
	}

	filterBig := false
	if v, ok := dataSearch["filter_big_or_all_course"]; ok {
		switch t := v.(type) {
		case string:
			if strings.TrimSpace(t) == "1" {
				filterBig = true
			}
		case float64:
			if int(t) == 1 {
				filterBig = true
			}
		}
	}

	n := len(filtered)
	resultsCh := make(chan MetricSpot, n)
	wg := sync.WaitGroup{}

	workers := int(math.Max(2, float64(runtime.NumCPU()/2)))
	chunk := make(chan SpotFuture, workers*4)

	// worker pool
	for i := 0; i < workers; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for sf := range chunk {
				course := 0.0
				if sf.Spot1Ask > 0 && sf.Market2Bid > 0 {
					course = ((sf.Market2Bid / sf.Spot1Ask) - 1) * 100
				}
				spread := sf.Spread
				val := spread
				if filterCourse {
					val = course
				}
				resultsCh <- MetricSpot{S: sf, CourseVal: course, SpreadVal: spread, MetricSort: val}
			}
		}()
	}

	// feeding
	go func() {
		for _, sf := range filtered {
			chunk <- sf
		}
		close(chunk)
	}()

	// collector
	go func() {
		wg.Wait()
		close(resultsCh)
	}()

	for r := range resultsCh {
		recs = append(recs, r)
	}

	// 4️⃣ Параллельная сортировка (ускорение ×2–3)
	 // ✅ фикс chunkSize — предотвращает slice bounds out of range
    chunks := int(math.Min(float64(runtime.NumCPU()), 4))
    if len(recs) < chunks {
        chunks = len(recs)
    }
    if chunks == 0 {
        return []interface{}{}, dataSearch, active
    }
    chunkSize := (len(recs) + chunks - 1) / chunks

	var sortWg sync.WaitGroup
	for i := 0; i < chunks; i++ {
		start := i * chunkSize
		end := start + chunkSize
		if end > len(recs) {
			end = len(recs)
		}
		sortWg.Add(1)
		go func(start, end int) {
			defer sortWg.Done()
			sort.Slice(recs[start:end], func(i, j int) bool {
				a, b := recs[start+i], recs[start+j]
				if a.MetricSort == b.MetricSort {
					return a.CourseVal > b.CourseVal
				}
				return a.MetricSort > b.MetricSort
			})
		}(start, end)
	}
	sortWg.Wait()

	// финальный merge-pass (гарантирует стабильный порядок)
	sort.SliceStable(recs, func(i, j int) bool {
		if recs[i].MetricSort == recs[j].MetricSort {
			return recs[i].CourseVal > recs[j].CourseVal
		}
		return recs[i].MetricSort > recs[j].MetricSort
	})

	// 5️⃣ Дедуп и сбор финального списка
	seen := map[string]struct{}{}
	inlines := make([]interface{}, 0, len(recs))
	for _, r := range recs {
		sf := r.S
		if _, ok := seen[sf.Symbol]; ok {
			continue
		}
		seen[sf.Symbol] = struct{}{}

		if filterCourse {
			if filterBig && r.CourseVal <= 0 {
				continue
			}
			inlines = append(inlines, buildInlineButtonSpotFuture(sf, true, r.CourseVal))
		} else {
			if filterBig && r.SpreadVal <= 0 {
				continue
			}
			inlines = append(inlines, buildInlineButtonSpotFuture(sf, false, r.SpreadVal))
		}
	}

	return inlines, dataSearch, active
}

// getUserSpots: same as getUserSpreads but for spots, supports marketsOverride same way.
func getUserSpots(spots []SpotFuture, accounts []User, tgid string, dataSearchParam *string, marketsOverride map[string]int) ([]interface{}, map[string]interface{}, bool) {
	active := false
	for _, acc := range accounts {
		if acc.Tgid == tgid {
			if (acc.IsActive == "1" && acc.IsActiveAdmin == "2") || acc.IsActiveAdmin == "1" || acc.TestActive == "1" {
				active = true
			} else {
				return []interface{}{}, map[string]interface{}{}, false
			}

			// markets override
			marketsSpot := acc.ListMarketsSpot
			if marketsOverride != nil && len(marketsOverride) > 0 {
				marketsSpot = marketsOverride
			}

			dataSearch := acc.DataSearch
			if dataSearchParam != nil {
				ds := parseJSONMap(*dataSearchParam)
				if len(ds) > 0 {
					dataSearch = ds
				}
			}

			blackset := acc.Blacklist
			dsRaw, _ := jsonFast.MarshalToString(dataSearch)

			// choose pre-sorted view
			filterCourse := false
			if v, ok := dataSearch["filter_course_or_spread"]; ok {
				switch t := v.(type) {
				case string:
					if strings.TrimSpace(t) == "1" {
						filterCourse = true
					}
				case float64:
					if int(t) == 1 {
						filterCourse = true
					}
				}
			}

			if filterCourse {
				exp := getCachedSpotsExpandedByCourse()
				if exp != nil && len(exp) > 0 {
					inlines, ds, act := filterSpotsExpanded(exp, marketsSpot, string(dsRaw), blackset, active)
					return inlines, ds, act
				}
			} else {
				exp := getCachedSpotsExpandedBySpread()
				if exp != nil && len(exp) > 0 {
					inlines, ds, act := filterSpotsExpanded(exp, marketsSpot, string(dsRaw), blackset, active)
					return inlines, ds, act
				}
			}

			inlines, ds, act := filterSpots(spots, marketsSpot, string(dsRaw), blackset, active)
			return inlines, ds, act
		}
	}
	return []interface{}{}, map[string]interface{}{}, false
}


// ------------------- Bot handlers: handleSpread / handleSpotFuture / handleDex -------------------

func handleSpread(u *User, s Spread, now time.Time) {
	if isBlacklisted(u, s.Symbol) {
		return
	}
	m1 := u.ListMarketsFutures[strings.ToUpper(strings.TrimSpace(s.Market1))]
	m2 := u.ListMarketsFutures[strings.ToUpper(strings.TrimSpace(s.Market2))]
	if m1 != 1 || m2 != 1 {
		return
	}
	hasSetting := func(k string) (bool, interface{}) {
		if u.DataSearch == nil {
			return false, nil
		}
		v, ok := u.DataSearch[k]
		if !ok {
			return false, nil
		}
		if sstr, isStr := v.(string); isStr && strings.ToLower(strings.TrimSpace(sstr)) == "no" {
			return false, nil
		}
		return true, v
	}
	spreadVal := s.Spread

	// direct course value (Market1Bid / Market2Ask)
	courseVal := s.Spread
	if s.Market1Bid > 0 && s.Market2Ask > 0 {
		courseVal = ((s.Market1Bid / s.Market2Ask) - 1) * 100.0
	}

	condSpreadDirect := false
	if ok, raw := hasSetting("spread"); ok {
		thr := floatFromData(raw)
		if thr <= spreadVal {
			condSpreadDirect = true
		}
	}
	condCourseDirect := false
	if ok, raw := hasSetting("course_spread"); ok {
		thr := floatFromData(raw)
		if thr <= courseVal {
			condCourseDirect = true
		}
	}
	if condSpreadDirect || condCourseDirect {
		key := fmt.Sprintf("%s_%s_%s_future", s.Symbol, s.Market2, s.Market1)
		last, ok := u.LastCoins[key]
		if !ok || now.Sub(last).Seconds() > FOUR_HOURS_SECONDS {
			u.LastCoins[key] = now
			// push to Redis (db0)
			notify := spreadNotification{Spread: s, Reverse: false, Tgid: u.Tgid}
			if err := pushNotificationGeneric(0, "Notifications:Spreads", notify); err != nil {
				log.Printf("pushNotification spread error: %v", err)
			}
			// persist last coins blob (update DB) — compress and save
			cleaned, compressed := cleanLastCoins(u.LastCoins)
			u.LastCoins = cleaned
			if err := persistLastCoins(u.Tgid, compressed); err != nil {
				log.Printf("persistLastCoins error: %v", err)
			}
		}
	}

	// reverse direction
	condSpreadReverse := false
	if ok, raw := hasSetting("spread"); ok {
		thr := floatFromData(raw)
		if thr <= (s.Market2Funding - s.Market1Funding) {
			condSpreadReverse = true
		}
	}

	// === добавлено: вычисление курсового спреда для реверса ===
	courseValReverse := s.Spread
	if s.Market2Bid > 0 && s.Market1Ask > 0 {
		courseValReverse = ((s.Market2Bid / s.Market1Ask) - 1) * 100.0
	}
	condCourseReverse := false
	if ok, raw := hasSetting("course_spread"); ok {
		thr := floatFromData(raw)
		if thr <= courseValReverse {
			condCourseReverse = true
		}
	}
	// ========================================================

	if condSpreadReverse || condCourseReverse {
		key := fmt.Sprintf("%s_%s_%s_future", s.Symbol, s.Market1, s.Market2)
		last, ok := u.LastCoins[key]
		if !ok || now.Sub(last).Seconds() > FOUR_HOURS_SECONDS {
			u.LastCoins[key] = now
			notify := spreadNotification{Spread: s, Reverse: true, Tgid: u.Tgid}
			if err := pushNotificationGeneric(0, "Notifications:Spreads", notify); err != nil {
				log.Printf("pushNotification spread reverse error: %v", err)
			}
			cleaned, compressed := cleanLastCoins(u.LastCoins)
			u.LastCoins = cleaned
			if err := persistLastCoins(u.Tgid, compressed); err != nil {
				log.Printf("persistLastCoins error: %v", err)
			}
		}
	}
}


func handleSpotFuture(u *User, sf SpotFuture, now time.Time) {
	if isBlacklisted(u, sf.Symbol) {
		return
	}
	m1 := u.ListMarketsSpot[strings.ToUpper(strings.TrimSpace(sf.Market1))]
	m2 := u.ListMarketsSpot[strings.ToUpper(strings.TrimSpace(sf.Market2))]
	if m1 != 1 || m2 != 1 {
		return
	}
	hasSetting := func(k string) (bool, interface{}) {
		if u.DataSearch == nil {
			return false, nil
		}
		v, ok := u.DataSearch[k]
		if !ok {
			return false, nil
		}
		if sstr, isStr := v.(string); isStr && strings.ToLower(strings.TrimSpace(sstr)) == "no" {
			return false, nil
		}
		return true, v
	}
	courseVal := 0.0
	if sf.Spot1Ask > 0 && sf.Market2Bid > 0 {
		courseVal = ((sf.Market2Bid / sf.Spot1Ask) - 1) * 100.0
	}
	spreadVal := sf.Spread
	cond1 := false
	if ok, raw := hasSetting("course_spread"); ok {
		thr := floatFromData(raw)
		if thr <= courseVal {
			cond1 = true
		}
	}
	cond2 := false
	if ok, raw := hasSetting("spread"); ok {
		thr := floatFromData(raw)
		if thr <= spreadVal {
			cond2 = true
		}
	}
	if cond1 || cond2 {
		key := fmt.Sprintf("%s_%s_%s_spot", sf.Symbol, sf.Market1, sf.Market2)
		last, ok := u.LastCoins[key]
		if !ok || now.Sub(last).Seconds() > FOUR_HOURS_SECONDS {
			u.LastCoins[key] = now
			notify := spotNotification{SpotFuture: sf, Tgid: u.Tgid}
			if err := pushNotificationGeneric(1, "Notifications:SpotFutures", notify); err != nil {
				log.Printf("pushNotification spot error: %v", err)
			}
			cleaned, compressed := cleanLastCoins(u.LastCoins)
			u.LastCoins = cleaned
			if err := persistLastCoins(u.Tgid, compressed); err != nil {
				log.Printf("persistLastCoins error: %v", err)
			}
		}
	}
}

func handleDex(u *User, d Dex, now time.Time) {
	// extract token key matching Python extract_token_key: "BSC_SIRENUSDT" -> "SIRENUSDT"
	tokenKey := extractDexTokenKey(d.Symbol)
	if tokenKey != "" {
		if _, ok := u.DexBlacklist[tokenKey]; ok {
			return
		}
	}
	if _, ok := u.DexBlacklist[strings.ToUpper(d.Symbol)]; ok {
		return
	}
	if isBlacklisted(u, d.Symbol) {
		return
	}
	hasSetting := func(k string) (bool, interface{}) {
		if u.DataSearch == nil {
			return false, nil
		}
		v, ok := u.DataSearch[k]
		if !ok {
			return false, nil
		}
		if sstr, isStr := v.(string); isStr {
			if strings.ToLower(strings.TrimSpace(sstr)) == "no" {
				return false, nil
			}
		}
		return true, v
	}
	okGt, rawGt := hasSetting("dex_diff_gt")
	okLt, rawLt := hasSetting("dex_diff_lt")
	if !okGt && !okLt {
		return
	}
	diffVal := d.Diff
	notify := false
	if okGt {
		thr := floatFromData(rawGt)
		if diffVal > thr {
			notify = true
		}
	}
	if okLt {
		thr := floatFromData(rawLt)
		if diffVal < thr {
			notify = true
		}
	}
	if !notify {
		return
	}
	// ensure cex market allowed in either futures or spot lists
	if u.ListMarketsFutures[strings.ToUpper(strings.TrimSpace(d.Market2))] != 1 &&
		u.ListMarketsSpot[strings.ToUpper(strings.TrimSpace(d.Market2))] != 1 {
		return
	}
	key := fmt.Sprintf("%s_%s_%s_dex", d.Symbol, "DEX", d.Market2)
	last, ok := u.LastCoins[key]
	if !ok || now.Sub(last).Seconds() > FOUR_HOURS_SECONDS {
		u.LastCoins[key] = now
		notify := dexNotification{Dex: d, Tgid: u.Tgid}
		if err := pushNotificationGeneric(2, "Notifications:Dex", notify); err != nil {
			log.Printf("pushNotification dex error: %v", err)
		}
		cleaned, compressed := cleanLastCoins(u.LastCoins)
		u.LastCoins = cleaned
		if err := persistLastCoins(u.Tgid, compressed); err != nil {
			log.Printf("persistLastCoins error: %v", err)
		}
	}
}

// processUser runs three handlers over spreads/spots/dex (background bot)
func processUser(u *User, spreads []Spread, spots []SpotFuture, dex []Dex) {
	now := time.Now()
	_ = copyLastCoins(u.LastCoins)
	for _, s := range spreads {
		handleSpread(u, s, now)
	}
	for _, sf := range spots {
		handleSpotFuture(u, sf, now)
	}
	for _, d := range dex {
		handleDex(u, d, now)
	}
}

// ------------------- UTILITIES / PARSING / PAGINATION -------------------

func parseJSONMap(raw string) map[string]interface{} {
	out := map[string]interface{}{}
	if raw == "" || raw == "no" {
		return out
	}
	_ = jsonFast.Unmarshal([]byte(raw), &out)
	return out
}

// parseListMarketsParam parses comma-separated "1,0,1,..." (in marketsOrder order)
// into map[string]int where key is UPPER(market) and value is 1 or 0.
func parseListMarketsParam(raw string) map[string]int {
	out := map[string]int{}
	if strings.TrimSpace(raw) == "" {
		return out
	}
	parts := strings.Split(raw, ",")
	for i := 0; i < len(parts) && i < len(marketsOrder); i++ {
		part := strings.TrimSpace(parts[i])
		val := 0
		if part == "1" {
			val = 1
		}
		out[strings.ToUpper(marketsOrder[i])] = val
	}
	// ensure all markets present (missing -> 0)
	for _, m := range marketsOrder {
		um := strings.ToUpper(m)
		if _, ok := out[um]; !ok {
			out[um] = 0
		}
	}
	return out
}

// buildDataSearchFromParams builds JSON string from GET params sort & lt.
// returns (jsonStr, present) where present==true if any of fields were provided.
func buildDataSearchFromParams(sortParam, ltParam string) (string, bool) {
	ds := map[string]interface{}{}
	if sortParam != "" {
		switch strings.ToLower(strings.TrimSpace(sortParam)) {
		case "funding":
			// use course/entry mode
			ds["filter_course_or_spread"] = "0"
		case "spread":
			ds["filter_course_or_spread"] = "1"
		}
	}
	if ltParam != "" {
		if strings.TrimSpace(ltParam) == "1" {
			ds["filter_big_or_all_course"] = "1"
		} else {
			ds["filter_big_or_all_course"] = "0"
		}
	}
	if len(ds) == 0 {
		return "", false
	}
	b, _ := jsonFast.MarshalToString(ds)
	return b, true
}

func parseMarketString(raw string) map[string]int {
	m := map[string]int{}
	if raw == "" || raw == "no" {
		return m
	}
	var arr []string
	if err := jsonFast.Unmarshal([]byte(raw), &arr); err != nil {
		arr = []string{}
		for _, part := range strings.Split(raw, ",") {
			part = strings.TrimSpace(strings.Trim(part, `[]"`))
			if part != "" {
				arr = append(arr, part)
			}
		}
	}
	for _, s := range arr {
		s = strings.TrimSpace(s)
		parts := strings.Split(s, "_")
		if len(parts) != 2 {
			continue
		}
		val := 0
		if parts[1] == "1" {
			val = 1
		}
		m[strings.ToUpper(parts[0])] = val
	}
	return m
}

// parseCompressedSet: zlib/json/plain -> set map
func parseCompressedSet(raw []byte) map[string]struct{} {
	out := map[string]struct{}{}
	if len(raw) == 0 {
		return out
	}
	if string(raw) == "no" {
		return out
	}
	var decompressed []byte
	r, err := zlib.NewReader(bytes.NewReader(raw))
	if err == nil {
		defer r.Close()
		var buf bytes.Buffer
		_, _ = buf.ReadFrom(r)
		decompressed = buf.Bytes()
	} else {
		decompressed = raw
	}
	var maybe map[string]interface{}
	if err := jsonFast.Unmarshal(decompressed, &maybe); err == nil {
		for k := range maybe {
			out[strings.ToUpper(strings.TrimSpace(k))] = struct{}{}
		}
		return out
	}
	var maybeArr []string
	if err := jsonFast.Unmarshal(decompressed, &maybeArr); err == nil {
		for _, v := range maybeArr {
			v = strings.TrimSpace(v)
			if v != "" {
				out[strings.ToUpper(v)] = struct{}{}
			}
		}
		return out
	}
	txt := strings.TrimSpace(string(decompressed))
	if txt == "" {
		return out
	}
	for _, part := range strings.Split(txt, ",") {
		part = strings.TrimSpace(part)
		if part != "" {
			out[strings.ToUpper(part)] = struct{}{}
		}
	}
	return out
}

func isBlacklisted(u *User, sym string) bool {
	if u == nil || len(u.Blacklist) == 0 {
		return false
	}
	s := strings.ToUpper(strings.TrimSpace(sym))
	_, ok := u.Blacklist[s]
	return ok
}

func parseSet(raw string) map[string]struct{} {
	s := map[string]struct{}{}
	if raw == "" {
		return s
	}
	var try interface{}
	if strings.HasPrefix(raw, "{") || strings.HasPrefix(raw, "[") {
		if err := jsonFast.Unmarshal([]byte(raw), &try); err == nil {
			switch tt := try.(type) {
			case map[string]interface{}:
				for k := range tt {
					s[k] = struct{}{}
				}
				return s
			case []interface{}:
				for _, v := range tt {
					if sv, ok := v.(string); ok && sv != "" {
						s[sv] = struct{}{}
					}
				}
				return s
			}
		}
	}
	for _, item := range strings.Split(raw, ",") {
		item = strings.TrimSpace(item)
		if item != "" {
			s[item] = struct{}{}
		}
	}
	return s
}

// Pagination helpers
func paginateSpreads(items []interface{}, currentPage int, itemsPerPage int, pagesPerRequest int) map[string]interface{} {
	totalItems := len(items)
	if itemsPerPage <= 0 {
		itemsPerPage = 5
	}
	if itemsPerPage > 200 {
		itemsPerPage = 200
	}
	totalPages := 0
	if totalItems > 0 {
		totalPages = (totalItems + itemsPerPage - 1) / itemsPerPage
	}
	if currentPage < 1 {
		currentPage = 1
	} else if currentPage > totalPages && totalPages > 0 {
		currentPage = totalPages
	}
	startPage := currentPage - pagesPerRequest
	if startPage < 1 {
		startPage = 1
	}
	endPage := currentPage + pagesPerRequest
	if endPage > totalPages {
		endPage = totalPages
	}
	pagesData := make([]map[string]interface{}, 0)
	for page := startPage; page <= endPage; page++ {
		startIdx := (page - 1) * itemsPerPage
		endIdx := startIdx + itemsPerPage
		if startIdx > totalItems {
			startIdx = totalItems
		}
		if endIdx > totalItems {
			endIdx = totalItems
		}
		pageItems := items[startIdx:endIdx]
		pagesData = append(pagesData, map[string]interface{}{
			"page":  page,
			"items": pageItems,
		})
	}
	return map[string]interface{}{
		"status":            "active",
		"current_page":      currentPage,
		"total_pages":       totalPages,
		"items_per_page":    itemsPerPage,
		"pages_per_request": pagesPerRequest,
		"start_page":        startPage,
		"end_page":          endPage,
		"has_prev":          currentPage > 1,
		"has_next":          currentPage < totalPages,
		"pages":             pagesData,
	}
}

// paginateAllSpreads for pages endpoint
func paginateAllSpreads(items []interface{}, itemsPerPage int) map[string]interface{} {
	totalItems := len(items)
	if itemsPerPage <= 0 {
		itemsPerPage = 5
	}
	if itemsPerPage > 200 {
		itemsPerPage = 200
	}
	totalPages := 0
	if totalItems > 0 {
		totalPages = (totalItems + itemsPerPage - 1) / itemsPerPage
	}
	pages := make([]map[string]interface{}, 0, totalPages)
	for p := 0; p < totalPages; p++ {
		start := p * itemsPerPage
		end := start + itemsPerPage
		if end > totalItems {
			end = totalItems
		}
		pages = append(pages, map[string]interface{}{
			"page":     p + 1,
			"items":    items[start:end],
			"has_prev": p > 0,
			"has_next": p < totalPages-1,
		})
	}
	return map[string]interface{}{
		"items_per_page": itemsPerPage,
		"total_pages":    totalPages,
		"pages":          pages,
	}
}
// ------------------- small helpers for pages endpoints -------------------

func fetchSpreadsSymbolCached(spreads []Spread, symbol string) []Spread {
	out := make([]Spread, 0)
	for _, s := range spreads {
		// symbol may be with or without suffix
		if strings.EqualFold(s.Symbol, symbol) || strings.HasPrefix(strings.ToUpper(s.Symbol), strings.ToUpper(symbol)) {
			out = append(out, s)
		}
	}
	return out
}
func fetchSpotSpreadsSymbolCached(spots []SpotFuture, symbol string) []SpotFuture {
	out := make([]SpotFuture, 0)
	for _, s := range spots {
		if strings.EqualFold(s.Symbol, symbol) || strings.HasPrefix(strings.ToUpper(s.Symbol), strings.ToUpper(symbol)) {
			out = append(out, s)
		}
	}
	return out
}

func filterSpreadsForPages(spreads []Spread, marketsDict map[string]int, dataSearchRaw string, blacklist map[string]struct{}) []interface{} {
	// Stage1: apply market availability and blacklist
	filtered := make([]Spread, 0, len(spreads))
	for _, s := range spreads {
		if marketsDict[strings.ToUpper(strings.TrimSpace(s.Market1))] == 0 ||
			marketsDict[strings.ToUpper(strings.TrimSpace(s.Market2))] == 0 {
			continue
		}
		if _, ok := blacklist[strings.ToUpper(strings.TrimSpace(s.Symbol))]; ok {
			continue
		}
		filtered = append(filtered, s)
	}

	// parse dataSearch
	var dataSearch map[string]interface{}
	if dataSearchRaw == "" || dataSearchRaw == "no" {
		dataSearch = map[string]interface{}{}
	} else {
		_ = jsonFast.UnmarshalFromString(dataSearchRaw, &dataSearch)
		if dataSearch == nil {
			dataSearch = map[string]interface{}{}
		}
	}

	if len(filtered) == 0 {
		return []interface{}{}
	}

	// expand directions (normal + reverse) — keep the Spread and attach dir
	type rec struct {
		S   Spread
		Dir string
	}
	recs := make([]rec, 0, len(filtered)*2)
	for _, s := range filtered {
		recs = append(recs, rec{S: s, Dir: "normal"})
		recs = append(recs, rec{S: s, Dir: "reverse"})
	}

	// compute primary metric for sorting per-record (taking direction into account)
	type metricRec struct {
		R      rec
		Metric float64
		Second float64
	}
	mr := make([]metricRec, 0, len(recs))
	for _, r := range recs {
		var metric float64
		if dataSearch["filter_course_or_spread"] == "1" {
			// course: use entry depending on direction
			if r.Dir == "normal" {
				metric = checkSpreadFutures(r.S)
			} else {
				metric = checkSpreadFuturesReverse(r.S)
			}
		} else {
			// default: use spread or funding diff consistent with takeSecondReverse
			if r.Dir == "normal" {
				metric = r.S.Spread
			} else {
				metric = r.S.Market2Funding - r.S.Market1Funding
			}
		}
		second := r.S.Spread
		mr = append(mr, metricRec{R: r, Metric: metric, Second: second})
	}

	// sort desc by Metric, tie-breaker second
	sort.SliceStable(mr, func(i, j int) bool {
		if mr[i].Metric == mr[j].Metric {
			return mr[i].Second > mr[j].Second
		}
		return mr[i].Metric > mr[j].Metric
	})

	// Build output list applying "big only" filters if present.
	// For pages we must return the same strings/ids as Python's build_inline_button_markets_futures / negative:
	// normal label: "{market2} - {market1}: {spread}% | {((market1bid/market2ask)-1)*100}"
	// normal id:   "id{ID}_{market2}_{market1}_{symbol}"  (we don't have DB id -> use 0)
	// reverse label: "{market1} - {market2}: {market2funding - market1funding}% | {((market2bid/market1ask)-1)*100}"
	// reverse id:   "id{ID}_{market1}_{market2}_{symbol}"
	out := make([]interface{}, 0, len(mr))
	for _, item := range mr {
		s := item.R.S
		dir := item.R.Dir

		// apply "big only" checks corresponding to Python:
		if dataSearch["filter_course_or_spread"] == "1" {
			// filter by entry
			if dataSearch["filter_big_or_all_course"] == "1" {
				if dir == "normal" {
					if checkSpreadFutures(s) <= 0 {
						continue
					}
				} else {
					if checkSpreadFuturesReverse(s) <= 0 {
						continue
					}
				}
			}
		} else {
			// default branch: if filter_big_or_all_course == '1' ensure entry>0 (approx using checkSpreadFutures)
			if dataSearch["filter_big_or_all_course"] == "1" {
				if dir == "normal" {
					if checkSpreadFutures(s) <= 0 {
						continue
					}
				} else {
					if checkSpreadFuturesReverse(s) <= 0 {
						continue
					}
				}
			}
		}

        // подготовка суффикса времени (если времена отличаются)
        timeSuffix := ""
        if s.Market1Time != s.Market2Time && (s.Market1Time != 0 || s.Market2Time != 0) {
            // предполагаем, что Market1Time/Market2Time — int (или int64)
            timeSuffix = fmt.Sprintf(" 🕓")
        }

		// build label + id according to direction
		if dir == "normal" {
			// compute entry calc = (market1bid / market2ask - 1) * 100
			var entry float64
			if s.Market1Bid != 0 && s.Market2Ask != 0 {
				entry = ((s.Market1Bid / s.Market2Ask) - 1) * 100
			} else {
				entry = 0
			}
			label := fmt.Sprintf("%s - %s: %.2f%% | %.2f", s.Market2, s.Market1, s.Spread, entry)
			label = label + timeSuffix
			id := fmt.Sprintf("id%d_%s_%s_%s", 0, s.Market2, s.Market1, s.Symbol)
			out = append(out, []string{label, id})
		} else {
			// reverse: funding diff and entry calc using market2bid/market1ask
			fundDiff := s.Market2Funding - s.Market1Funding
			var entry float64
			if s.Market2Bid != 0 && s.Market1Ask != 0 {
				entry = ((s.Market2Bid / s.Market1Ask) - 1) * 100
			} else {
				entry = 0
			}
			label := fmt.Sprintf("%s - %s: %.2f%% | %.2f", s.Market1, s.Market2, fundDiff, entry)
			label = label + timeSuffix
			id := fmt.Sprintf("id%d_%s_%s_%s", 0, s.Market1, s.Market2, s.Symbol)
			out = append(out, []string{label, id})
		}
	}

	return out
}
// filterSpotsForPages — apply user's spot-markets/dataSearch/blacklist but DO NOT dedupe.
// Returns []interface{} where each element is []string{label, id} matching Python build_inline_button_markets_spot_futures.
func filterSpotsForPages(spots []SpotFuture, marketsDict map[string]int, dataSearchRaw string, blacklist map[string]struct{}) []interface{} {
	// Stage1: filter by markets & blacklist
	filtered := make([]SpotFuture, 0, len(spots))
	for _, s := range spots {
		if marketsDict[strings.ToUpper(strings.TrimSpace(s.Market1))] == 0 ||
			marketsDict[strings.ToUpper(strings.TrimSpace(s.Market2))] == 0 {
			continue
		}
		if _, ok := blacklist[strings.ToUpper(strings.TrimSpace(s.Symbol))]; ok {
			continue
		}
		filtered = append(filtered, s)
	}

	// parse dataSearch
	var dataSearch map[string]interface{}
	if dataSearchRaw == "" || dataSearchRaw == "no" {
		dataSearch = map[string]interface{}{}
	} else {
		_ = jsonFast.UnmarshalFromString(dataSearchRaw, &dataSearch)
		if dataSearch == nil {
			dataSearch = map[string]interface{}{}
		}
	}

	if len(filtered) == 0 {
		return []interface{}{}
	}

	// build sortable records
	type rec struct {
		S      SpotFuture
		Metric float64
		Course float64
	}
	recs := make([]rec, 0, len(filtered))
	for _, sf := range filtered {
		courseVal := 0.0
		if sf.Spot1Ask > 0 && sf.Market2Bid > 0 {
			courseVal = ((sf.Market2Bid / sf.Spot1Ask) - 1) * 100.0
		}
		metric := sf.Spread
		if dataSearch["filter_course_or_spread"] == "1" {
			metric = courseVal
		}
		recs = append(recs, rec{S: sf, Metric: metric, Course: courseVal})
	}

	// sort desc by Metric (tie-breaker Course)
	sort.SliceStable(recs, func(i, j int) bool {
		if recs[i].Metric == recs[j].Metric {
			return recs[i].Course > recs[j].Course
		}
		return recs[i].Metric > recs[j].Metric
	})

	out := make([]interface{}, 0, len(recs))
	for _, r := range recs {
		sf := r.S
		// apply 'big only' filtering
		if dataSearch["filter_big_or_all_course"] == "1" {
			if dataSearch["filter_course_or_spread"] == "1" {
				var entry float64
				if sf.Market2Bid != 0 && sf.Spot1Ask != 0 {
					entry = ((sf.Market2Bid / sf.Spot1Ask) - 1) * 100
				} else {
					entry = 0
				}
				if entry <= 0 {
					continue
				}
			} else {
				var entry float64
				if sf.Market2Bid != 0 && sf.Spot1Ask != 0 {
					entry = ((sf.Market2Bid / sf.Spot1Ask) - 1) * 100
				} else {
					entry = 0
				}
				if entry <= 0 {
					continue
				}
			}
		}

		// label: "{market1} - {market2}: {market2funding}% | {((market2bid/spot1ask)-1)*100}  вход"
		var entry float64
		if sf.Market2Bid != 0 && sf.Spot1Ask != 0 {
			entry = ((sf.Market2Bid / sf.Spot1Ask) - 1) * 100
		} else {
			entry = 0
		}
		label := fmt.Sprintf("%s - %s: %.2f%% | %.2f вход", sf.Market1, sf.Market2, sf.Market2Funding, entry)
		id := fmt.Sprintf("spotid%d_%s_%s_%s", 0, sf.Market1, sf.Market2, sf.Symbol)
		out = append(out, []string{label, id})
	}
	return out
}

// getSpreadBySymbolAndMarketsCachedOptimized: сначала отфильтровать по префиксу символа, затем по markets (order-agnostic).
func getSpreadBySymbolAndMarketsCachedOptimized(spreads []Spread, symbol, m1, m2 string) *Spread {
	sub := fetchSpreadsSymbolCached(spreads, symbol)
	for i := range sub {
		s := &sub[i]
		if (strings.EqualFold(s.Market1, m1) && strings.EqualFold(s.Market2, m2)) ||
			(strings.EqualFold(s.Market1, m2) && strings.EqualFold(s.Market2, m1)) {
			return s
		}
	}
	return nil
}

// getSpotSpreadBySymbolAndMarketsCachedOptimized: для спота order-sensitive (мы ищем Market1==m1 && Market2==m2)
func getSpotSpreadBySymbolAndMarketsCachedOptimized(spots []SpotFuture, symbol, m1, m2 string) *SpotFuture {
	sub := fetchSpotSpreadsSymbolCached(spots, symbol)
	for i := range sub {
		s := &sub[i]
		if strings.EqualFold(s.Market1, m1) && strings.EqualFold(s.Market2, m2) {
			return s
		}
	}
	return nil
}


// createMessageToFutures / createMessageToSpot similar to original formatting
func createMessageToFutures(bot Spread, m1 string) map[string]interface{} {
	// determine direction
	reversed := false
	longFunding := bot.Market2Funding
	shortFunding := bot.Market1Funding
	longTime := int(bot.Market2Time)
	shortTime := int(bot.Market1Time)
	entry := checkSpreadFutures(bot)
	exit := checkExitSpreadFutures(bot)
	if strings.EqualFold(m1, bot.Market1) {
		// flip
		entry = checkSpreadFuturesReverse(bot)
		exit = checkExitSpreadFuturesReverse(bot)
		longFunding, shortFunding = bot.Market1Funding, bot.Market2Funding
		longTime, shortTime = int(bot.Market1Time), int(bot.Market2Time)
		reversed = true
	}

	// icon/top coin logic (по объёму)
	maxVol := bot.Amount24M1
	if bot.Amount24M2 > maxVol {
		maxVol = bot.Amount24M2
	}
	icon := "🔴"
	if maxVol > 1_000_000 {
		icon = "🟢"
	} else if maxVol > 200_000 {
		icon = "🟡"
	}

	// links map (subset, как в Python)
	futuresLinks := map[string]func(string) string{
		"Bybit": func(sym string) string { return fmt.Sprintf("https://www.bybit.com/trade/usdt/%s", sym) },
		"Mexc": func(sym string) string { return fmt.Sprintf("https://futures.mexc.com/ru-RU/exchange/%s?type=linear_swap", strings.ReplaceAll(sym, "USDT", "_USDT")) },
		"Kucoin": func(sym string) string { return fmt.Sprintf("https://www.kucoin.com/ru/futures/trade/%s", strings.ReplaceAll(sym, "USDT", "USDTM")) },
		"Gateio": func(sym string) string { return fmt.Sprintf("https://www.gate.io/ru/futures/USDT/%s", strings.ReplaceAll(sym, "USDT", "_USDT")) },
		"Bitget": func(sym string) string { return fmt.Sprintf("https://www.bitget.com/ru/futures/usdt/%s", sym) },
		"Huobi": func(sym string) string { return fmt.Sprintf("https://www.htx.com/futures/linear_swap/exchange#contract_code=%s&contract_type=swap&type=cross", strings.ReplaceAll(sym, "USDT", "-USDT")) },
		"Okx": func(sym string) string { return fmt.Sprintf("https://www.okx.com/ru/trade-swap/%s", strings.ToLower(strings.ReplaceAll(sym, "USDT", "-USDT-SWAP"))) },
		"Binance": func(sym string) string { return fmt.Sprintf("https://www.binance.com/ru/futures/%s", sym) },
		"BingX": func(sym string) string { return fmt.Sprintf("https://swap.bingx.com/ru-ru/%s", strings.ReplaceAll(sym, "USDT", "-USDT")) },
		"BitMart": func(sym string) string { return fmt.Sprintf("https://derivatives.bitmart.com/ru-RU?symbol=%s&theme=dark", sym) },
		"Poloniex": func(sym string) string { return fmt.Sprintf("https://poloniex.com/futures/trade/%s", strings.ReplaceAll(sym, "USDT", "USDTPERP")) },
		"CoinEx": func(sym string) string { return fmt.Sprintf("https://www.coinex.com/ru/futures/%s", strings.ToLower(strings.ReplaceAll(sym, "USDT", "-USDT"))) },
		"Ourbit": func(sym string) string { return fmt.Sprintf("https://futures.ourbit.com/ru-RU/exchange/%s?type=linear_swap", strings.ReplaceAll(sym, "USDT", "_USDT")) },
		"Hyperliquid": func(sym string) string { return fmt.Sprintf("https://app.hyperliquid.xyz/trade/%s", strings.ReplaceAll(sym, "USDT", "")) },
		"LBank": func(sym string) string { return fmt.Sprintf("https://www.lbank.com/futures/%s", strings.ToLower(sym)) },
		"Aster": func(sym string) string { return fmt.Sprintf("https://www.asterdex.com/ru/trade/pro/futures/%s", sym) },
		"XT": func(sym string) string { return fmt.Sprintf("https://www.xt.com/ru/futures/trade/%s", strings.ToLower(strings.ReplaceAll(sym, "USDT", "_USDT"))) },
		"WEEX": func(sym string) string { return fmt.Sprintf("https://www.weex.com/futures/%s", strings.ReplaceAll(sym, "USDT", "-USDT")) },
		"Phemex": func(sym string) string { return fmt.Sprintf("https://phemex.com/futures/%s", strings.ReplaceAll(sym, "USDT", "-USDT")) },
		"BinanceAlpha": func(sym string) string {
			contracts := getBACached()
			if info, ok := contracts[sym]; ok {
				addr := info["contract_address"]
				chain := info["chain_name"]
				if addr != "" {
					return fmt.Sprintf("https://www.binance.com/en/alpha/%s/%s", chain, addr)
				}
			}
			return "https://www.binance.com/en/alpha"
		},
	}

	// helpers to get link or empty
	getLink := func(market, sym string) string {
		if f, ok := futuresLinks[market]; ok {
			return f(sym)
		}
		return ""
	}
	symbol := bot.Symbol

	// build response skeleton
	result := map[string]interface{}{
		"coin":     bot.Symbol,
		"icon":     icon,
		"reversed": reversed,
		"markets": map[string]interface{}{
			"long":  map[string]interface{}{},
			"short": map[string]interface{}{},
		},
		"spread": map[string]interface{}{},
	}

	// fill markets and spread according to direction
	if !reversed {
		result["markets"] = map[string]interface{}{
			"long": map[string]interface{}{
				"market":          bot.Market2,
				"link":            getLink(bot.Market2, symbol),
				"funding_current": longFunding,
				"volume24":        fmtAmountUSD(bot.Amount24M2),
				"limit":           math.Round(bot.LimitsM2),
				"funding_target":  bot.IsDeviation2,
				"time":            longTime,
			},
			"short": map[string]interface{}{
				"market":          bot.Market1,
				"link":            getLink(bot.Market1, symbol),
				"funding_current": shortFunding,
				"volume24":        fmtAmountUSD(bot.Amount24M1),
				"limit":           math.Round(bot.LimitsM1),
				"funding_target":  bot.IsDeviation1,
				"time":            shortTime,
			},
		}

		cur := math.Round((bot.Market1Funding - bot.Market2Funding)*10000) / 10000
		// special-case Hyperliquid/Aster rounding logic from python
		if (bot.Market2 == "Hyperliquid" || bot.Market2 == "Aster") || (bot.Market1 == "Hyperliquid" || bot.Market1 == "Aster") {
			cur = math.Round((bot.Market1Funding - bot.Market2Funding)*10000) / 10000
		}
		result["spread"] = map[string]interface{}{
			"current":   cur,
			"fee":       math.Round((bot.Market1Fee+bot.Market2Fee)*100) / 100,
			"entry":     math.Round(entry*100) / 100,
			"exit":      math.Round(exit*100) / 100,
			"entry_raw": []float64{bot.Market1Bid, bot.Market2Ask},
			"exit_raw":  []float64{bot.Market1Ask, bot.Market2Bid},
		}
	} else {
		// reversed
		result["markets"] = map[string]interface{}{
			"long": map[string]interface{}{
				"market":          bot.Market1,
				"link":            getLink(bot.Market1, symbol),
				"funding_current": longFunding,
				"volume24":        fmtAmountUSD(bot.Amount24M1),
				"limit":           math.Round(bot.LimitsM1),
				"funding_target":  bot.IsDeviation1,
				"time":            longTime,
			},
			"short": map[string]interface{}{
				"market":          bot.Market2,
				"link":            getLink(bot.Market2, symbol),
				"funding_current": shortFunding,
				"volume24":        fmtAmountUSD(bot.Amount24M2),
				"limit":           math.Round(bot.LimitsM2),
				"funding_target":  bot.IsDeviation2,
				"time":            shortTime,
			},
		}

		cur := math.Round((bot.Market2Funding - bot.Market1Funding)*10000) / 10000
		if (bot.Market2 == "Hyperliquid" || bot.Market2 == "Aster") || (bot.Market1 == "Hyperliquid" || bot.Market1 == "Aster") {
			cur = math.Round((bot.Market2Funding - bot.Market1Funding)*10000) / 10000
		}
		result["spread"] = map[string]interface{}{
			"current":   cur,
			"fee":       math.Round((bot.Market1Fee+bot.Market2Fee)*100) / 100,
			"entry":     math.Round(entry*100) / 100,
			"exit":      math.Round(exit*100) / 100,
			"entry_raw": []float64{bot.Market2Bid, bot.Market1Ask},
			"exit_raw":  []float64{bot.Market2Ask, bot.Market1Bid},
		}
	}

	return result
}


func createMessageToSpot(sf SpotFuture) map[string]interface{} {
	// coin name without USDT
	coin := strings.ReplaceAll(sf.Symbol, "USDT", "")

	// determine top_coin by volumes (amount24m2, amount24spot)
	maxVol := sf.Amount24M2
	if sf.Amount24Spot > maxVol {
		maxVol = sf.Amount24Spot
	}
	topCoin := "🔴"
	if maxVol > 1_000_000 {
		topCoin = "🟢"
	} else if maxVol > 200_000 {
		topCoin = "🟡"
	}

	// market links (spot + futures) — subset from Python mapping
	marketLinks := map[string]map[string]string{
		"Bybit": {
			"spot":    fmt.Sprintf("https://www.bybit.com/ru-RU/trade/spot/%s/USDT", coin),
			"futures": fmt.Sprintf("https://www.bybit.com/trade/usdt/%s", sf.Symbol),
		},
		"Mexc": {
			"spot":    fmt.Sprintf("https://www.mexc.com/ru-RU/exchange/%s_USDT?_from=search_spot_trade", coin),
			"futures": fmt.Sprintf("https://futures.mexc.com/ru-RU/exchange/%s?type=linear_swap", strings.ReplaceAll(sf.Symbol, "USDT", "_USDT")),
		},
		"Kucoin": {
			"spot":    fmt.Sprintf("https://www.kucoin.com/ru/trade/%s-USDT", coin),
			"futures": fmt.Sprintf("https://www.kucoin.com/ru/futures/trade/%s", strings.ReplaceAll(sf.Symbol, "USDT", "USDTM")),
		},
		"Gateio": {
			"spot":    fmt.Sprintf("https://www.gate.io/ru/trade/%s_USDT", coin),
			"futures": fmt.Sprintf("https://www.gate.io/ru/futures/USDT/%s", strings.ReplaceAll(sf.Symbol, "USDT", "_USDT")),
		},
		"Bitget": {
			"spot":    fmt.Sprintf("https://www.bitget.com/ru/spot/%s", sf.Symbol),
			"futures": fmt.Sprintf("https://www.bitget.com/ru/futures/usdt/%s", sf.Symbol),
		},
		"Huobi": {
			"spot":    fmt.Sprintf("https://www.htx.com/trade/%s?_type=spot", strings.ToLower(strings.ReplaceAll(sf.Symbol, "USDT", "_USDT"))),
			"futures": fmt.Sprintf("https://www.htx.com/futures/linear_swap/exchange#contract_code=%s&contract_type=swap&type=cross", strings.ReplaceAll(sf.Symbol, "USDT", "-USDT")),
		},
		"Okx": {
			"spot":    fmt.Sprintf("https://www.okx.com/ru/trade-spot/%s", strings.ToLower(strings.ReplaceAll(sf.Symbol, "USDT", "-usdt"))),
			"futures": fmt.Sprintf("https://www.okx.com/ru/trade-swap/%s", strings.ToLower(strings.ReplaceAll(sf.Symbol, "USDT", "-usdt-swap"))),
		},
		"Binance": {
			"spot":    fmt.Sprintf("https://www.binance.com/ru/trade/%s_USDT", coin),
			"futures": fmt.Sprintf("https://www.binance.com/ru/futures/%s", sf.Symbol),
		},
		"BingX": {
			"spot":    fmt.Sprintf("https://bingx.com/ru-ru/spot/%s/", sf.Symbol),
			"futures": fmt.Sprintf("https://swap.bingx.com/ru-ru/%s", strings.ReplaceAll(sf.Symbol, "USDT", "-USDT")),
		},
		"BitMart": {
			"spot":    fmt.Sprintf("https://www.bitmart.com/trade/ru-RU?symbol=%s_USDT", coin),
			"futures": fmt.Sprintf("https://derivatives.bitmart.com/ru-RU?symbol=%s&theme=dark", sf.Symbol),
		},
		"Poloniex": {
			"spot":    fmt.Sprintf("https://poloniex.com/trade/%s_USDT/?type=spot", coin),
			"futures": fmt.Sprintf("https://poloniex.com/futures/trade/%s", strings.ReplaceAll(sf.Symbol, "USDT", "USDTPERP")),
		},
		"CoinEx": {
			"spot":    fmt.Sprintf("https://www.coinex.com/ru/exchange/%s", strings.ToLower(strings.ReplaceAll(sf.Symbol, "USDT", "-USDT"))),
			"futures": fmt.Sprintf("https://www.coinex.com/ru/futures/%s", strings.ToLower(strings.ReplaceAll(sf.Symbol, "USDT", "-USDT"))),
		},
        "Ourbit": {
                "spot":    fmt.Sprintf("https://www.ourbit.com/ru-RU/exchange/%s", strings.ReplaceAll(sf.Symbol, "USDT", "_USDT")),
                "futures": fmt.Sprintf("https://futures.ourbit.com/ru-RU/exchange/%s", strings.ReplaceAll(sf.Symbol, "USDT", "_USDT")),
            },
		"Hyperliquid": {
			"spot":    fmt.Sprintf("https://app.hyperliquid.xyz/trade/%s", coin),
			"futures": fmt.Sprintf("https://app.hyperliquid.xyz/trade/%s", coin),
		},
		"LBank": {
			"spot":    fmt.Sprintf("https://www.lbank.com/trade/%s_usdt", strings.ToLower(coin)),
			"futures": fmt.Sprintf("https://www.lbank.com/futures/%s", strings.ToLower(coin)),
		},
		"Aster": {
			"spot":    fmt.Sprintf("https://www.asterdex.com/ru/trade/pro/spot/%s", sf.Symbol),
			"futures": fmt.Sprintf("https://www.asterdex.com/ru/trade/pro/futures/%s", sf.Symbol),
		},
        "XT": {
			"spot":    fmt.Sprintf("https://www.xt.com/ru/trade/%s", strings.ToLower(strings.ReplaceAll(sf.Symbol, "USDT", "_usdt"))),
			"futures": fmt.Sprintf("https://www.xt.com/ru/futures/trade/%s", strings.ToLower(strings.ReplaceAll(sf.Symbol, "USDT", "_usdt"))),
		},
        "WEEX": {
			"spot":    fmt.Sprintf("https://www.weex.com/spot/%s", strings.ReplaceAll(sf.Symbol, "USDT", "-USDT")),
			"futures": fmt.Sprintf("https://www.weex.com/futures/%s", strings.ReplaceAll(sf.Symbol, "USDT", "-USDT")),
		},
        "Phemex": {
			"spot":    fmt.Sprintf("https://phemex.com/trade/%s", strings.ReplaceAll(sf.Symbol, "USDT", "-USDT")),
			"futures": fmt.Sprintf("https://phemex.com/futures/%s", strings.ReplaceAll(sf.Symbol, "USDT", "-USDT")),
		},
        "BinanceAlpha": func() map[string]string {
			contracts := getBACached()
			if info, ok := contracts[sf.Symbol]; ok {
				addr := info["contract_address"]
				chain := info["chain_name"]
				if addr != "" {
					link := fmt.Sprintf("https://www.binance.com/en/alpha/%s/%s", chain, addr)
					return map[string]string{"spot": link, "futures": link}
				}
			}
			return map[string]string{"spot": "https://www.binance.com/en/alpha", "futures": "https://www.binance.com/en/alpha"}
		}(),
	}

	// pick links safely
	getMarketLink := func(market, kind string) string {
		if mm, ok := marketLinks[market]; ok {
			if link, ok2 := mm[kind]; ok2 {
				return link
			}
		}
		return ""
	}

	// build result
	result := map[string]interface{}{
		"symbol":   sf.Symbol,
		"top_coin": topCoin,
		"market1": map[string]interface{}{
			"name": sf.Market1,
			"link": getMarketLink(sf.Market1, "spot"),
			"side": "BUY",
		},
		"market2": map[string]interface{}{
			"name": sf.Market2,
			"link": getMarketLink(sf.Market2, "futures"),
			"side": "SHORT",
		},
		"spread": map[string]interface{}{
			"current":     sf.Spread,
			"volume24_m1": fmtAmountUSD(sf.Amount24Spot),
			"volume24_m2": fmtAmountUSD(sf.Amount24M2),
			"predicted":   func() interface{} { if sf.Market2Predict == "" { return nil }; return sf.Market2Predict }(),
			"limit":       math.Round(sf.LimitsM2),
			"tendency":    func() interface{} { if sf.IsDeviation2 == 0 { return nil }; return sf.IsDeviation2 }(),
			"time_h":      math.Round(sf.Market2Time),
		},
		"fees": map[string]interface{}{
			"m1_fee": sf.Market1Fee,
			"m2_fee": sf.Market2Fee,
			"total":  math.Round((sf.Market1Fee+sf.Market2Fee)*100) / 100,
		},
		"entry_spread": map[string]interface{}{
			"value": math.Round((((sf.Market2Bid / sf.Spot1Ask) - 1) * 100)*100) / 100,
			"bid":   sf.Market2Bid,
			"ask":   sf.Spot1Ask,
		},
		"exit_spread": map[string]interface{}{
			"value": math.Round((((sf.Market2Ask / sf.Spot1Bid) - 1) * 100)*100) / 100,
			"bid":   sf.Market2Ask,
			"ask":   sf.Spot1Bid,
		},
	}

	return result
}


// ------------------- USER FILTERS used by bot -------------------

func filterActiveUsersBot(users []User) []User {
	var filtered []User
	for _, u := range users {
		active := (u.IsActive == "1" && u.IsActiveAdmin == "2") || u.IsActiveAdmin == "1" || u.TestActive == "1"
		if active {
			filtered = append(filtered, u)
		}
	}
	return filtered
}

func filterMonitoringUsers(users []User) []User {
	var filtered []User
	for _, u := range users {
		ds := u.DataSearch
		if ds == nil {
			continue
		}
		if (ds["spread"] != nil && ds["spread"] != "no") ||
			(ds["course_spread"] != nil && ds["course_spread"] != "no") ||
			(ds["dex_diff_gt"] != nil && ds["dex_diff_gt"] != "no") ||
			(ds["dex_diff_lt"] != nil && ds["dex_diff_lt"] != "no") {
			filtered = append(filtered, u)
		}
	}
	return filtered
}

// ------------------- DEX API HANDLERS -------------------

// parseDexSymbol splits "BSC_SIRENUSDT" into chain="BSC", display="SIREN"
func parseDexSymbol(raw string) (chain, display string) {
	if parts := strings.SplitN(raw, "_", 2); len(parts) == 2 {
		chain = parts[0]
		display = strings.TrimSuffix(parts[1], "USDT")
		return
	}
	return "", strings.TrimSuffix(raw, "USDT")
}

// extractDexTokenKey mirrors Python's extract_token_key:
// "BSC_SIRENUSDT" -> split by "_" -> "SIRENUSDT" -> strip "USDT" -> "SIREN" -> add "USDT" -> "SIRENUSDT"
// This normalized key is what's stored in the blacklist.
func extractDexTokenKey(symbol string) string {
	s := strings.ToUpper(strings.TrimSpace(symbol))
	tokenPart := s
	if idx := strings.Index(s, "_"); idx >= 0 {
		tokenPart = s[idx+1:]
	}
	tokenPart = strings.TrimSuffix(tokenPart, "USDT")
	// keep only alphanumeric chars
	var b strings.Builder
	for _, ch := range tokenPart {
		if ch >= 'A' && ch <= 'Z' || ch >= '0' && ch <= '9' {
			b.WriteRune(ch)
		}
	}
	core := b.String()
	if core == "" {
		return ""
	}
	return core + "USDT"
}

// filterDexByBlacklist filters DEX entries by blacklist — matches Python filter_spreads_dex logic.
// Checks both full symbol and extractDexTokenKey (matches Python extract_token_key).
func filterDexByBlacklist(dex []Dex, blacklist map[string]struct{}) []Dex {
	filtered := make([]Dex, 0, len(dex))
	for _, d := range dex {
		fullSym := strings.ToUpper(strings.TrimSpace(d.Symbol))
		if _, ok := blacklist[fullSym]; ok {
			continue
		}
		tokenKey := extractDexTokenKey(d.Symbol)
		if tokenKey != "" {
			if _, ok := blacklist[tokenKey]; ok {
				continue
			}
		}
		filtered = append(filtered, d)
	}
	return filtered
}

// /api/dex?user_id=123&page=0&items=5&sort=spread&lt=1
// Level 1: list of coins (deduped by symbol), format like Telegram bot
// Matches Python filter_spreads_dex: markets + blacklist + sort + dedup
func handleDexAPI(w http.ResponseWriter, r *http.Request) {
	userID := r.URL.Query().Get("user_id")
	pageStr := r.URL.Query().Get("page")
	itemsStr := r.URL.Query().Get("items")
	sortParam := r.URL.Query().Get("sort") // "spread" or "funding"
	ltParam := r.URL.Query().Get("lt")     // "1" = positive only

	page := 0
	if pageStr != "" {
		p, _ := strconv.Atoi(pageStr)
		page = p
	}
	currentPage := page
	if currentPage < 1 {
		currentPage = 1
	}
	items := 5
	if itemsStr != "" {
		if it, err := strconv.Atoi(itemsStr); err == nil && it >= 1 {
			items = it
			if items > 200 {
				items = 200
			}
		}
	}

	accounts := getCachedUsers()

	var userAcc *User
	for i := range accounts {
		if accounts[i].Tgid == userID {
			userAcc = &accounts[i]
			break
		}
	}
	if userAcc == nil {
		jsonResponse(w, map[string]interface{}{"status": "no_sub"})
		return
	}
	if !((userAcc.IsActive == "1" && userAcc.IsActiveAdmin == "2") || userAcc.IsActiveAdmin == "1" || userAcc.TestActive == "1") {
		jsonResponse(w, map[string]interface{}{"status": "no_sub"})
		return
	}

	// Use pre-sorted view (matches TwoSortedSpreadsExpanded pattern for futures/spots)
	var entries []dexEntry
	if sortParam == "funding" {
		entries = getCachedDexExpandedByFunding()
	} else {
		entries = getCachedDexExpandedByDiff()
	}
	if entries == nil {
		entries = nil // fallback: will be rebuilt below
	}

	// If pre-sorted view unavailable, build from raw cache
	if len(entries) == 0 {
		dex := getCachedDex()
		entries = make([]dexEntry, 0, len(dex))
		for _, d := range dex {
			if sortParam == "funding" {
				entries = append(entries, dexEntry{d: d, primary: d.FundingRate, secondary: d.Diff})
			} else {
				entries = append(entries, dexEntry{d: d, primary: d.Diff, secondary: d.FundingRate})
			}
		}
		sort.SliceStable(entries, func(i, j int) bool {
			if entries[i].primary == entries[j].primary {
				return entries[i].secondary > entries[j].secondary
			}
			return entries[i].primary > entries[j].primary
		})
	}

	// Filter + dedup in one pass over pre-sorted array (O(N), matches Python filter_spreads_dex)
	// Python checks: markets_dict_futures[s[2]] (DEX) and markets_dict_futures[s[3]] (cex_market)
	// and extract_token_key(s[1]) not in blacklist_dex
	seenSymbols := map[string]struct{}{}
	result := make([]interface{}, 0, len(entries))
	for i := range entries {
		e := &entries[i]

		// Blacklist check (matches Python extract_token_key)
		tokenKey := extractDexTokenKey(e.d.Symbol)
		if tokenKey != "" {
			if _, ok := userAcc.DexBlacklist[tokenKey]; ok {
				continue
			}
		}
		fullSym := strings.ToUpper(strings.TrimSpace(e.d.Symbol))
		if _, ok := userAcc.DexBlacklist[fullSym]; ok {
			continue
		}

		// Market filtering (matches Python: both DEX and cex_market must be enabled)
		if userAcc.ListMarketsFutures["DEX"] != 1 {
			continue
		}
		if userAcc.ListMarketsFutures[strings.ToUpper(strings.TrimSpace(e.d.Market2))] != 1 {
			continue
		}

		// lt=1: positive only filter — always by Diff (вход), matching Python's
		// check_spread_futures_dex(spread) <= 0 which checks spread[6] = diff
		if ltParam == "1" && e.d.Diff <= 0 {
			continue
		}

		// Dedup by symbol (matches Python: first occurrence wins after sort)
		if _, ok := seenSymbols[e.d.Symbol]; ok {
			continue
		}
		seenSymbols[e.d.Symbol] = struct{}{}

		// Build label (matches Python build_inline_button_spread_in_dex / spread_of_funding_dex)
		chain, display := parseDexSymbol(e.d.Symbol)
		var label string
		if sortParam == "funding" {
			label = fmt.Sprintf("%s [%s]: %.2f%% фанд", display, chain, e.d.FundingRate)
		} else {
			label = fmt.Sprintf("%s [%s]: %.2f вход", display, chain, e.d.Diff)
		}
		id := fmt.Sprintf("dexsymbol_%s", e.d.Symbol)
		result = append(result, []string{label, id})
	}

	if len(result) == 0 {
		jsonResponse(w, map[string]interface{}{"status": "empty"})
		return
	}
	resp := paginateSpreads(result, currentPage, items, 20)
	jsonResponse(w, resp)
}

// /api/dex_pages?user_id=...&symbol=BSC_SIRENUSDT&items=5&sort=spread&lt=1
// Level 2: for a given symbol, show market pairs like "Kucoin: 0.01% | 29.4 вход"
func handleDexPages(w http.ResponseWriter, r *http.Request) {
	userID := r.URL.Query().Get("user_id")
	symbol := r.URL.Query().Get("symbol")
	sortParam := r.URL.Query().Get("sort")
	ltParam := r.URL.Query().Get("lt")
	itemsStr := r.URL.Query().Get("items")
	items := 5
	if itemsStr != "" {
		if it, err := strconv.Atoi(itemsStr); err == nil && it > 0 {
			items = it
		}
	}

	dex := getCachedDex()
	accounts := getCachedUsers()

	var userAcc *User
	for i := range accounts {
		if accounts[i].Tgid == userID {
			userAcc = &accounts[i]
			break
		}
	}
	if userAcc == nil {
		jsonResponse(w, map[string]interface{}{"status": "no_sub"})
		return
	}

	// exact match on symbol
	filtered := make([]Dex, 0)
	for _, d := range dex {
		if strings.EqualFold(d.Symbol, symbol) {
			fullSym := strings.ToUpper(strings.TrimSpace(d.Symbol))
			if _, ok := userAcc.DexBlacklist[fullSym]; ok {
				continue
			}
			tokenKey := extractDexTokenKey(d.Symbol)
			if tokenKey != "" {
				if _, ok := userAcc.DexBlacklist[tokenKey]; ok {
					continue
				}
			}
			filtered = append(filtered, d)
		}
	}

	// sort by funding or diff
	sort.SliceStable(filtered, func(i, j int) bool {
		if sortParam == "funding" {
			return filtered[i].FundingRate > filtered[j].FundingRate
		}
		return filtered[i].Diff > filtered[j].Diff
	})

	// build labels: "Kucoin: 0.01% | 29.4 вход"
	inlines := make([]interface{}, 0, len(filtered))
	for _, d := range filtered {
		label := fmt.Sprintf("%s: %.2f%% | %.2f", d.Market2, d.FundingRate, d.Diff)
		if ltParam != "1" || d.Diff > 0 {
			id := fmt.Sprintf("dexid_%s_%s", d.Market2, d.Symbol)
			inlines = append(inlines, []string{label, id})
		}
	}

	if len(inlines) == 0 {
		jsonResponse(w, map[string]interface{}{"status": "empty"})
		return
	}
	resp := paginateAllSpreads(inlines, items)
	chain, display := parseDexSymbol(symbol)
	response := map[string]interface{}{
		"status":      "active",
		"symbol":      symbol, // raw symbol (e.g., "BSCONUSDT") — frontend uses this for pagination
		"displayName": fmt.Sprintf("%s [%s]", display, chain), // display name (e.g., "ON [BSC]")
	}
	for k, v := range resp {
		response[k] = v
	}
	jsonResponse(w, response)
}

// /api/dex_id?user_id=...&symbol=BSC_SIRENUSDT&market=Kucoin
// Level 3: detailed info for a specific DEX pair
func handleDexID(w http.ResponseWriter, r *http.Request) {
	userID := r.URL.Query().Get("user_id")
	findSymbol := r.URL.Query().Get("symbol")
	findMarket := r.URL.Query().Get("market")

	dex := getCachedDex()
	accounts := getCachedUsers()

	var userAcc *User
	for i := range accounts {
		if accounts[i].Tgid == userID {
			userAcc = &accounts[i]
			break
		}
	}
	if userAcc == nil {
		jsonResponse(w, map[string]interface{}{"status": "no_sub"})
		return
	}

	for _, d := range dex {
		if strings.EqualFold(d.Symbol, findSymbol) && strings.EqualFold(d.Market2, findMarket) {
			chain, display := parseDexSymbol(d.Symbol)
			// dexscreener link
			cleanSymbol := strings.TrimSuffix(d.Symbol, "USDT")
			dexLink := fmt.Sprintf("https://dexscreener.com/search?q=%s", cleanSymbol)

			result := map[string]interface{}{
				"symbol":      d.Symbol,
				"displayName": fmt.Sprintf("%s [%s]", display, chain),
				"market":      d.Market2,
				"bid":         d.Bid,
				"priceUsd":    d.PriceUsd,
				"diff":        d.Diff,
				"contract":    d.Contract,
				"chain":       d.Chain,
				"volume24":    d.Volume24,
				"volume24Cex": d.Volume24Cex,
				"dexId":       d.DexId,
				"url":         d.URL,
				"dexLink":     dexLink,
				"cexAsk":      d.CexAsk,
				"fundingRate": d.FundingRate,
				"isUpdated":   d.IsUpdated,
			}
			jsonResponse(w, map[string]interface{}{"status": "ok", "data": result})
			return
		}
	}
	jsonResponse(w, map[string]interface{}{"status": "empty"})
}

// /api/top_funding — public cached top-16 coins by funding rate (no auth required)
func handleTopFunding(w http.ResponseWriter, r *http.Request) {
	coins := getCachedTopFunding()
	if coins == nil {
		jsonResponse(w, map[string]interface{}{"status": "reloading"})
		return
	}
	jsonResponse(w, map[string]interface{}{
		"status": "ok",
		"coins":  coins,
	})
}

// /api/top_funding_spot — public cached top-16 spot/futures coins by funding rate
func handleTopFundingSpot(w http.ResponseWriter, r *http.Request) {
	coins := getCachedTopFundingSpot()
	if coins == nil {
		jsonResponse(w, map[string]interface{}{"status": "reloading"})
		return
	}
	jsonResponse(w, map[string]interface{}{
		"status": "ok",
		"coins":  coins,
	})
}

// ------------------- MISC HELPERS -------------------
// fmtAmountUSD — удобное форматирование суммы (1_200 -> "1.20K", 1_200_000 -> "1.20M", ...)
func fmtAmountUSD(v float64) string {
	if v <= 0 {
		return "0"
	}
	switch {
	case v >= 1_000_000_000:
		return fmt.Sprintf("%.2fB", v/1_000_000_000)
	case v >= 1_000_000:
		return fmt.Sprintf("%.2fM", v/1_000_000)
	case v >= 1_000:
		return fmt.Sprintf("%.2fK", v/1_000)
	default:
		// no decimals for small numbers
		return fmt.Sprintf("%.0f", v)
	}
}


func jsonResponse(w http.ResponseWriter, data interface{}) {
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(data)
}

func getEnv(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}


// ------------------- MAIN -------------------

func main() {
	log.Println("Starting combined service (API + funding bot + cacher)...")

	// init connections (best-effort)
	if err := initRedisClients(); err != nil {
		log.Printf("initial redis init warning: %v", err)
	}
	if err := initDB(); err != nil {
		log.Printf("initial mysql init warning: %v", err)
	}

	// start background cacher (updates caches every 2s)
	ctxBg, cancel := context.WithCancel(context.Background())
	defer cancel()
	//go backgroundCacher(ctxBg, cacheInterval)

    if err := reloadSpreadsFromRedis(); err != nil { log.Printf("initial reload spreads: %v", err) }
    if err := reloadSpotsFromRedis(); err != nil { log.Printf("initial reload spots: %v", err) }
    if err := reloadDexFromRedis(); err != nil { log.Printf("initial reload dex: %v", err) }
    if err := reloadUsersFromDB(); err != nil { log.Printf("initial reload users: %v", err) }
    if err := reloadBAContracts(); err != nil { log.Printf("initial reload BA contracts: %v", err) }

    go startRedisSubscriber(ctxBg)

	// start funding bot loop (uses cache only)
	//go fundingBotLoop(ctxBg, cacheInterval)

	// HTTP handlers (read from cache only)
	http.HandleFunc("/api/futures", handleFutures)
	http.HandleFunc("/api/spot", handleSpot)
	http.HandleFunc("/api/dex", handleDexAPI)
	http.HandleFunc("/api/futures_pages", handleFuturesPages)
	http.HandleFunc("/api/spot_pages", handleSpotPages)
	http.HandleFunc("/api/dex_pages", handleDexPages)
	http.HandleFunc("/api/futures_id", handleFuturesID)
	http.HandleFunc("/api/spot_id", handleSpotID)
	http.HandleFunc("/api/dex_id", handleDexID)
	http.HandleFunc("/api/top_funding", handleTopFunding)
	http.HandleFunc("/api/top_funding_spot", handleTopFundingSpot)

	log.Printf("Listening on :%s", port)
	log.Fatal(http.ListenAndServe(":"+port, nil))
}
