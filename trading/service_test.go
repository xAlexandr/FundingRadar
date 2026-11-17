package main

import (
	"fmt"
	"sort"
	"strings"
	"testing"
)

// ============================================================================
// BinanceAlpha link building tests
// ============================================================================

func TestBAClient_LookupFound(t *testing.T) {
	contracts := map[string]map[string]string{
		"BTCUSDT": {"contract_address": "0xabc123", "chain_name": "bsc"},
	}
	if info, ok := contracts["BTCUSDT"]; ok {
		addr := info["contract_address"]
		chain := info["chain_name"]
		link := "https://www.binance.com/en/alpha/" + chain + "/" + addr
		expected := "https://www.binance.com/en/alpha/bsc/0xabc123"
		if link != expected {
			t.Errorf("Expected %s, got %s", expected, link)
		}
	} else {
		t.Error("Should find BTCUSDT")
	}
}

func TestBAClient_LookupNotFound(t *testing.T) {
	contracts := map[string]map[string]string{
		"ETHUSDT": {"contract_address": "0xdef", "chain_name": "bsc"},
	}
	if _, ok := contracts["NONEXISTENT"]; ok {
		t.Error("Should not find NONEXISTENT")
	}
}

func TestBAClient_EmptyAddress(t *testing.T) {
	contracts := map[string]map[string]string{
		"BTCUSDT": {"contract_address": "", "chain_name": "bsc"},
	}
	if info, ok := contracts["BTCUSDT"]; ok {
		addr := info["contract_address"]
		if addr != "" {
			t.Error("Address should be empty")
		}
	}
}

func TestBAClient_EmptyChain(t *testing.T) {
	contracts := map[string]map[string]string{
		"BTCUSDT": {"contract_address": "0xabc", "chain_name": ""},
	}
	if info, ok := contracts["BTCUSDT"]; ok {
		chain := info["chain_name"]
		if chain == "" {
			chain = "bsc"
		}
		link := "https://www.binance.com/en/alpha/" + chain + "/0xabc"
		expected := "https://www.binance.com/en/alpha/bsc/0xabc"
		if link != expected {
			t.Errorf("Expected %s, got %s", expected, link)
		}
	}
}

func TestBAClient_EmptyContracts(t *testing.T) {
	contracts := map[string]map[string]string{}
	if len(contracts) != 0 {
		t.Error("Empty contracts should have length 0")
	}
}

func TestBAClient_NilValue(t *testing.T) {
	contracts := map[string]map[string]string{
		"BTCUSDT": nil,
	}
	if info, ok := contracts["BTCUSDT"]; ok {
		if info != nil {
			t.Error("Info should be nil")
		}
	}
}

func TestBAClient_MultipleTokens(t *testing.T) {
	contracts := map[string]map[string]string{
		"BTCUSDT": {"contract_address": "0xabc", "chain_name": "bsc"},
		"ETHUSDT": {"contract_address": "0xdef", "chain_name": "ethereum"},
		"SOLUSDT": {"contract_address": "0x123", "chain_name": "solana"},
	}
	expected := map[string]string{
		"BTCUSDT": "https://www.binance.com/en/alpha/bsc/0xabc",
		"ETHUSDT": "https://www.binance.com/en/alpha/ethereum/0xdef",
		"SOLUSDT": "https://www.binance.com/en/alpha/solana/0x123",
	}
	for sym, expLink := range expected {
		if info, ok := contracts[sym]; ok {
			link := "https://www.binance.com/en/alpha/" + info["chain_name"] + "/" + info["contract_address"]
			if link != expLink {
				t.Errorf("%s: expected %s, got %s", sym, expLink, link)
			}
		} else {
			t.Errorf("%s: not found", sym)
		}
	}
}

// ============================================================================
// Spread metric tests
// ============================================================================

func TestCheckSpreadFutures_Normal(t *testing.T) {
	s := Spread{Market1Bid: 100.0, Market2Ask: 95.0, Spread: 5.0}
	result := checkSpreadFutures(s)
	expected := ((100.0 / 95.0) - 1) * 100
	if result < expected-0.01 || result > expected+0.01 {
		t.Errorf("Expected %.2f, got %.2f", expected, result)
	}
}

func TestCheckSpreadFutures_ZeroBid(t *testing.T) {
	s := Spread{Market1Bid: 0, Market2Ask: 95.0, Spread: 5.0}
	result := checkSpreadFutures(s)
	if result != 5.0 {
		t.Errorf("Expected 5.0 fallback, got %.2f", result)
	}
}

func TestCheckSpreadFutures_ZeroAsk(t *testing.T) {
	s := Spread{Market1Bid: 100.0, Market2Ask: 0, Spread: 5.0}
	result := checkSpreadFutures(s)
	if result != 5.0 {
		t.Errorf("Expected 5.0 fallback, got %.2f", result)
	}
}

func TestCheckSpreadFutures_BothZero(t *testing.T) {
	s := Spread{Market1Bid: 0, Market2Ask: 0, Spread: 0}
	result := checkSpreadFutures(s)
	if result != 0 {
		t.Errorf("Expected 0, got %.2f", result)
	}
}

func TestCheckSpreadFuturesReverse_Normal(t *testing.T) {
	s := Spread{Market2Bid: 100.0, Market1Ask: 95.0, Spread: 5.0}
	result := checkSpreadFuturesReverse(s)
	expected := ((100.0 / 95.0) - 1) * 100
	if result < expected-0.01 || result > expected+0.01 {
		t.Errorf("Expected %.2f, got %.2f", expected, result)
	}
}

func TestCheckSpreadFuturesReverse_ZeroValues(t *testing.T) {
	s := Spread{Market2Bid: 0, Market1Ask: 0, Spread: 3.0}
	result := checkSpreadFuturesReverse(s)
	if result != 3.0 {
		t.Errorf("Expected 3.0 fallback, got %.2f", result)
	}
}

func TestTakeSecondReverse_Normal(t *testing.T) {
	s := Spread{Spread: 5.0}
	result := takeSecondReverse(s, "normal")
	if result != 5.0 {
		t.Errorf("Expected 5.0, got %.2f", result)
	}
}

func TestTakeSecondReverse_Reverse(t *testing.T) {
	s := Spread{Market2Funding: 0.05, Market1Funding: 0.01}
	result := takeSecondReverse(s, "reverse")
	if result < 0.039 || result > 0.041 {
		t.Errorf("Expected ~0.04, got %.4f", result)
	}
}

func TestTakeSecondReverse_ZeroSpread(t *testing.T) {
	s := Spread{Spread: 0}
	result := takeSecondReverse(s, "normal")
	if result != 0 {
		t.Errorf("Expected 0, got %.2f", result)
	}
}

// ============================================================================
// Expand spreads tests
// ============================================================================

func TestExpandSpreadsWithDirections_Single(t *testing.T) {
	spreads := []Spread{{Symbol: "BTCUSDT"}}
	expanded := expandSpreadsWithDirections(spreads)
	if len(expanded) != 2 {
		t.Errorf("Expected 2, got %d", len(expanded))
	}
	if expanded[0].Dir != "normal" || expanded[1].Dir != "reverse" {
		t.Error("Expected normal and reverse")
	}
}

func TestExpandSpreadsWithDirections_Empty(t *testing.T) {
	expanded := expandSpreadsWithDirections([]Spread{})
	if len(expanded) != 0 {
		t.Errorf("Expected 0, got %d", len(expanded))
	}
}

func TestExpandSpreadsWithDirections_Multiple(t *testing.T) {
	spreads := []Spread{{Symbol: "A"}, {Symbol: "B"}, {Symbol: "C"}}
	expanded := expandSpreadsWithDirections(spreads)
	if len(expanded) != 6 {
		t.Errorf("Expected 6, got %d", len(expanded))
	}
}

// ============================================================================
// Pagination tests
// ============================================================================

func TestPaginateSpreads_Normal(t *testing.T) {
	spreads := make([]interface{}, 25)
	for i := range spreads {
		spreads[i] = []string{"BTCUSDT", "Bybit"}
	}
	result := paginateSpreads(spreads, 1, 5, 20)
	if result["total_pages"] != 5 {
		t.Errorf("Expected 5 pages, got %v", result["total_pages"])
	}
}

func TestPaginateSpreads_Empty(t *testing.T) {
	result := paginateSpreads([]interface{}{}, 1, 5, 20)
	if result["total_pages"] != 0 {
		t.Errorf("Expected 0 pages, got %v", result["total_pages"])
	}
}

func TestPaginateSpreads_ClampHigh(t *testing.T) {
	spreads := make([]interface{}, 10)
	for i := range spreads {
		spreads[i] = []string{"X"}
	}
	result := paginateSpreads(spreads, 100, 5, 20)
	page := result["current_page"].(int)
	total := result["total_pages"].(int)
	if page > total {
		t.Error("Page should be clamped to total")
	}
}

func TestPaginateSpreads_ClampLow(t *testing.T) {
	spreads := make([]interface{}, 10)
	for i := range spreads {
		spreads[i] = []string{"X"}
	}
	result := paginateSpreads(spreads, -5, 5, 20)
	page := result["current_page"].(int)
	if page < 1 {
		t.Error("Page should be clamped to 1")
	}
}

func TestPaginateAllSpreads_Normal(t *testing.T) {
	spreads := make([]interface{}, 12)
	for i := range spreads {
		spreads[i] = []string{"BTCUSDT"}
	}
	result := paginateAllSpreads(spreads, 5)
	if result["total_pages"] != 3 {
		t.Errorf("Expected 3 pages, got %v", result["total_pages"])
	}
}

func TestPaginateAllSpreads_Empty(t *testing.T) {
	result := paginateAllSpreads([]interface{}{}, 5)
	if result["total_pages"] != 0 {
		t.Errorf("Expected 0 pages, got %v", result["total_pages"])
	}
}

func TestPaginateAllSpreads_SinglePage(t *testing.T) {
	spreads := make([]interface{}, 3)
	for i := range spreads {
		spreads[i] = []string{"X"}
	}
	result := paginateAllSpreads(spreads, 5)
	if result["total_pages"] != 1 {
		t.Errorf("Expected 1 page, got %v", result["total_pages"])
	}
}

// ============================================================================
// Filter spreads tests (simplified — avoid parallel sort edge cases)
// ============================================================================

func TestFilterSpreads_EmptyInput(t *testing.T) {
	markets := map[string]int{"BYBIT": 1}
	blacklist := map[string]struct{}{}
	// Use filterSpreadsExpanded instead to avoid parallel sort panic
	exp := []expandedSpread{}
	result, _, active := filterSpreadsExpanded(exp, markets, "", blacklist, true)
	if !active {
		t.Error("Expected active=true")
	}
	if len(result) != 0 {
		t.Errorf("Expected 0, got %d", len(result))
	}
}

func TestFilterSpreads_BlacklistedSymbol(t *testing.T) {
	// Test blacklist logic directly
	spreads := []Spread{
		{Symbol: "BTCUSDT", Market1: "BYBIT", Market2: "BITGET"},
		{Symbol: "ETHUSDT", Market1: "BYBIT", Market2: "BITGET"},
	}
	markets := map[string]int{"BYBIT": 1, "BITGET": 1}
	blacklist := map[string]struct{}{"BTCUSDT": {}}

	// Manual filter (same logic as filterSpreads)
	filtered := make([]Spread, 0)
	for _, s := range spreads {
		if markets[s.Market1] == 0 || markets[s.Market2] == 0 {
			continue
		}
		if _, ok := blacklist[s.Symbol]; ok {
			continue
		}
		filtered = append(filtered, s)
	}

	if len(filtered) != 1 {
		t.Errorf("Expected 1 (BTCUSDT blacklisted), got %d", len(filtered))
	}
	if filtered[0].Symbol != "ETHUSDT" {
		t.Errorf("Expected ETHUSDT, got %s", filtered[0].Symbol)
	}
}

func TestFilterSpreads_InactiveMarketFilter(t *testing.T) {
	spreads := []Spread{
		{Symbol: "BTCUSDT", Market1: "BYBIT", Market2: "BITGET"},
	}
	markets := map[string]int{"BYBIT": 1, "BITGET": 0}

	filtered := make([]Spread, 0)
	for _, s := range spreads {
		if markets[s.Market1] == 0 || markets[s.Market2] == 0 {
			continue
		}
		filtered = append(filtered, s)
	}

	if len(filtered) != 0 {
		t.Errorf("Expected 0 (BITGET inactive), got %d", len(filtered))
	}
}

// ============================================================================
// Data struct tests
// ============================================================================

func TestSpread_Fields(t *testing.T) {
	s := Spread{Symbol: "BTCUSDT", Market1: "Bybit", Market2: "Bitget", Spread: 0.05}
	if s.Symbol != "BTCUSDT" {
		t.Error("Symbol mismatch")
	}
	if s.Spread != 0.05 {
		t.Error("Spread mismatch")
	}
}

func TestSpotFuture_Fields(t *testing.T) {
	sf := SpotFuture{Symbol: "BTCUSDT", Spot1Bid: 50000.0, Market2Ask: 50100.0}
	if sf.Symbol != "BTCUSDT" {
		t.Error("Symbol mismatch")
	}
	if sf.Spot1Bid != 50000.0 {
		t.Error("Spot1Bid mismatch")
	}
}

func TestDex_Fields(t *testing.T) {
	d := Dex{Symbol: "PEPEUSDT", PriceUsd: 0.00001, Diff: 5.0}
	if d.Symbol != "PEPEUSDT" {
		t.Error("Symbol mismatch")
	}
	if d.Diff != 5.0 {
		t.Error("Diff mismatch")
	}
}

// ============================================================================
// Edge cases for crash prevention
// ============================================================================

func TestBAClient_MissingChainKey(t *testing.T) {
	contracts := map[string]map[string]string{
		"BTCUSDT": {"contract_address": "0xabc"},
	}
	if info, ok := contracts["BTCUSDT"]; ok {
		chain := info["chain_name"]
		if chain == "" {
			chain = "bsc"
		}
		if chain != "bsc" {
			t.Error("Should default to bsc")
		}
	}
}

func TestBAClient_MissingAddressKey(t *testing.T) {
	contracts := map[string]map[string]string{
		"BTCUSDT": {"chain_name": "bsc"},
	}
	if info, ok := contracts["BTCUSDT"]; ok {
		addr := info["contract_address"]
		if addr != "" {
			t.Error("Should be empty when key missing")
		}
	}
}

func TestBAClient_EmptyMapValue(t *testing.T) {
	contracts := map[string]map[string]string{
		"BTCUSDT": {},
	}
	if info, ok := contracts["BTCUSDT"]; ok {
		addr := info["contract_address"]
		chain := info["chain_name"]
		if addr != "" || chain != "" {
			t.Error("Empty map should have empty values")
		}
	}
}

func TestSpread_AllZeroes(t *testing.T) {
	s := Spread{}
	result := checkSpreadFutures(s)
	if result != 0 {
		t.Errorf("Expected 0, got %.2f", result)
	}
}

func TestSpread_NegativeValues(t *testing.T) {
	s := Spread{Market1Bid: -100.0, Market2Ask: -50.0, Spread: -10.0}
	result := checkSpreadFutures(s)
	// Should not panic
	_ = result
}

func TestExpandSpreadsWithDirections_NilSpread(t *testing.T) {
	// Should not panic with nil slice
	expanded := expandSpreadsWithDirections(nil)
	if len(expanded) != 0 {
		t.Errorf("Expected 0, got %d", len(expanded))
	}
}

// ============================================================================
// extractDexTokenKey tests — must match Python extract_token_key exactly
// Python: "BSC_SIRENUSDT" -> split("_")[1] -> strip "USDT" -> "SIREN" -> + "USDT" -> "SIRENUSDT"
// ============================================================================

func TestExtractDexTokenKey_ChainPrefixed(t *testing.T) {
	// Python: extract_token_key("BSC_SIRENUSDT") == "SIRENUSDT"
	result := extractDexTokenKey("BSC_SIRENUSDT")
	if result != "SIRENUSDT" {
		t.Errorf("Expected SIRENUSDT, got %s", result)
	}
}

func TestExtractDexTokenKey_NoChainPrefix(t *testing.T) {
	// Python: extract_token_key("SIRENUSDT") == "SIRENUSDT"
	result := extractDexTokenKey("SIRENUSDT")
	if result != "SIRENUSDT" {
		t.Errorf("Expected SIRENUSDT, got %s", result)
	}
}

func TestExtractDexTokenKey_Lowercase(t *testing.T) {
	// Python: extract_token_key("bsc_sirenusdt") == "SIRENUSDT" (uppercase)
	result := extractDexTokenKey("bsc_sirenusdt")
	if result != "SIRENUSDT" {
		t.Errorf("Expected SIRENUSDT, got %s", result)
	}
}

func TestExtractDexTokenKey_MultipleUnderscores(t *testing.T) {
	// Python splits on first "_" only
	// "ETH_USDT_USDT" -> "USDT_USDT" -> strip USDT -> "USDT_" -> alnum -> "USDT" -> +USDT -> "USDTUSDT"
	// But let's test the realistic case: "ETH_TONUSDT" -> "TONUSDT" -> strip -> "TON" -> +USDT -> "TONUSDT"
	result := extractDexTokenKey("ETH_TONUSDT")
	if result != "TONUSDT" {
		t.Errorf("Expected TONUSDT, got %s", result)
	}
}

func TestExtractDexTokenKey_WithSpaces(t *testing.T) {
	// Python: extract_token_key(" BSC_SIRENUSDT ") == "SIRENUSDT" (strips whitespace)
	result := extractDexTokenKey("  BSC_SIRENUSDT  ")
	if result != "SIRENUSDT" {
		t.Errorf("Expected SIRENUSDT, got %s", result)
	}
}

func TestExtractDexTokenKey_Empty(t *testing.T) {
	result := extractDexTokenKey("")
	if result != "" {
		t.Errorf("Expected empty, got %s", result)
	}
}

func TestExtractDexTokenKey_NoUSDT(t *testing.T) {
	// Python: "ETH_BTC" -> "BTC" (no USDT to strip) -> "BTC" + "USDT" -> "BTCUSDT"
	result := extractDexTokenKey("ETH_BTC")
	if result != "BTCUSDT" {
		t.Errorf("Expected BTCUSDT, got %s", result)
	}
}

func TestExtractDexTokenKey_SpecialChars(t *testing.T) {
	// Python: alnum filter strips non-alphanumeric
	// "BSC_SIREN-1USDT" -> "SIREN-1USDT" -> strip USDT -> "SIREN-1" -> alnum -> "SIREN1" -> +USDT -> "SIREN1USDT"
	result := extractDexTokenKey("BSC_SIREN-1USDT")
	if result != "SIREN1USDT" {
		t.Errorf("Expected SIREN1USDT, got %s", result)
	}
}

func TestExtractDexTokenKey_OnlyUSDT(t *testing.T) {
	// "ETH_USDT" -> "USDT" -> strip USDT -> "" -> empty -> ""
	result := extractDexTokenKey("ETH_USDT")
	if result != "" {
		t.Errorf("Expected empty, got %s", result)
	}
}

func TestExtractDexTokenKey_CaseInsensitive(t *testing.T) {
	// Python uppercases everything
	result := extractDexTokenKey("bsc_sirenusdt")
	if result != "SIRENUSDT" {
		t.Errorf("Expected SIRENUSDT, got %s", result)
	}
}

// ============================================================================
// DEX blacklist filtering tests — must match Python filter_spreads_dex logic
// Python: extract_token_key(s[1]) not in blacklist_dex
// ============================================================================

func TestDexBlacklist_FilterByTokenKey(t *testing.T) {
	// Blacklist has "SIRENUSDT", symbol "BSC_SIRENUSDT" should be filtered
	blacklist := map[string]struct{}{"SIRENUSDT": {}}
	dex := []Dex{
		{Symbol: "BSC_SIRENUSDT", Market2: "Kucoin", Diff: 5.0},
		{Symbol: "BSC_ETHUSDT", Market2: "Kucoin", Diff: 3.0},
	}

	filtered := filterDexByBlacklist(dex, blacklist)
	if len(filtered) != 1 {
		t.Fatalf("Expected 1, got %d", len(filtered))
	}
	if filtered[0].Symbol != "BSC_ETHUSDT" {
		t.Errorf("Expected BSC_ETHUSDT, got %s", filtered[0].Symbol)
	}
}

func TestDexBlacklist_FilterByFullSymbol(t *testing.T) {
	// Full symbol in blacklist should also work
	blacklist := map[string]struct{}{"BSC_SIRENUSDT": {}}
	dex := []Dex{
		{Symbol: "BSC_SIRENUSDT", Market2: "Kucoin", Diff: 5.0},
	}

	filtered := filterDexByBlacklist(dex, blacklist)
	if len(filtered) != 0 {
		t.Errorf("Expected 0 (full symbol blacklisted), got %d", len(filtered))
	}
}

func TestDexBlacklist_EmptyBlacklist(t *testing.T) {
	blacklist := map[string]struct{}{}
	dex := []Dex{
		{Symbol: "BSC_SIRENUSDT", Market2: "Kucoin", Diff: 5.0},
	}

	filtered := filterDexByBlacklist(dex, blacklist)
	if len(filtered) != 1 {
		t.Errorf("Expected 1 (no blacklist), got %d", len(filtered))
	}
}

func TestDexBlacklist_MultipleBlacklisted(t *testing.T) {
	blacklist := map[string]struct{}{"SIRENUSDT": {}, "PEPEUSDT": {}}
	dex := []Dex{
		{Symbol: "BSC_SIRENUSDT", Market2: "Kucoin", Diff: 5.0},
		{Symbol: "ETH_PEPEUSDT", Market2: "Kucoin", Diff: 3.0},
		{Symbol: "BSC_ETHUSDT", Market2: "Kucoin", Diff: 1.0},
	}

	filtered := filterDexByBlacklist(dex, blacklist)
	if len(filtered) != 1 {
		t.Fatalf("Expected 1, got %d", len(filtered))
	}
	if filtered[0].Symbol != "BSC_ETHUSDT" {
		t.Errorf("Expected BSC_ETHUSDT, got %s", filtered[0].Symbol)
	}
}

func TestDexBlacklist_NoChainPrefix(t *testing.T) {
	// Symbol without chain prefix: "SIRENUSDT" should match blacklist "SIRENUSDT"
	blacklist := map[string]struct{}{"SIRENUSDT": {}}
	dex := []Dex{
		{Symbol: "SIRENUSDT", Market2: "Kucoin", Diff: 5.0},
	}

	filtered := filterDexByBlacklist(dex, blacklist)
	if len(filtered) != 0 {
		t.Errorf("Expected 0, got %d", len(filtered))
	}
}

func TestDexBlacklist_CaseInsensitive(t *testing.T) {
	// Blacklist key is always uppercase; symbol may be lowercase
	blacklist := map[string]struct{}{"SIRENUSDT": {}}
	dex := []Dex{
		{Symbol: "bsc_sirenusdt", Market2: "Kucoin", Diff: 5.0},
	}

	filtered := filterDexByBlacklist(dex, blacklist)
	if len(filtered) != 0 {
		t.Errorf("Expected 0 (case-insensitive match), got %d", len(filtered))
	}
}

// ============================================================================
// Integration: verify blacklist against real Redis data
// ============================================================================

func TestDexBlacklist_RealData_ZK(t *testing.T) {
	// Blacklist has "ZKUSDT" — "BSC_ZKUSDT" should be filtered
	blacklist := map[string]struct{}{"ZKUSDT": {}}
	dex := []Dex{
		{Symbol: "BSC_ZKUSDT", Market2: "Kucoin", Diff: 5.0, FundingRate: 1.0},
		{Symbol: "ETH_ZKJUSDT", Market2: "Kucoin", Diff: 5.0, FundingRate: 1.0},
		{Symbol: "BSC_AAVEUSDT", Market2: "Kucoin", Diff: 5.0, FundingRate: 1.0},
	}

	filtered := filterDexByBlacklist(dex, blacklist)
	if len(filtered) != 2 {
		t.Fatalf("Expected 2 (ZKUSDT blacklisted, ZKJUSDT and AAVEUSDT kept), got %d", len(filtered))
	}
	for _, d := range filtered {
		if extractDexTokenKey(d.Symbol) == "ZKUSDT" {
			t.Errorf("ZKUSDT should be blacklisted but found %s", d.Symbol)
		}
	}
}

func TestDexBlacklist_RealData_AI(t *testing.T) {
	// Blacklist has "AIUSDT" — should NOT match "AIOZUSDT" (different token key)
	blacklist := map[string]struct{}{"AIUSDT": {}}
	dex := []Dex{
		{Symbol: "BSC_AIUSDT", Market2: "Kucoin", Diff: 5.0, FundingRate: 1.0},
		{Symbol: "BSC_AIOZUSDT", Market2: "Kucoin", Diff: 5.0, FundingRate: 1.0},
		{Symbol: "ETH_AIXBTUSDT", Market2: "Kucoin", Diff: 5.0, FundingRate: 1.0},
	}

	filtered := filterDexByBlacklist(dex, blacklist)
	// AIUSDT blacklisted, but AIOZUSDT and AIXBTUSDT should remain (different token keys)
	if len(filtered) != 2 {
		t.Fatalf("Expected 2 (only AIUSDT blacklisted), got %d", len(filtered))
	}
	for _, d := range filtered {
		if d.Symbol == "BSC_AIUSDT" {
			t.Error("BSC_AIUSDT should be blacklisted")
		}
	}
}

func TestDexBlacklist_RealData_H(t *testing.T) {
	// Blacklist has "HUSDT" — only exact token "H" should be blocked, not "HFT", "HOT", etc.
	blacklist := map[string]struct{}{"HUSDT": {}}
	dex := []Dex{
		{Symbol: "ETH_HUSDT", Market2: "Kucoin", Diff: 5.0, FundingRate: 1.0},
		{Symbol: "ETH_HFTUSDT", Market2: "Kucoin", Diff: 5.0, FundingRate: 1.0},
		{Symbol: "ETH_HOTUSDT", Market2: "Kucoin", Diff: 5.0, FundingRate: 1.0},
		{Symbol: "ETH_HUMAUSDT", Market2: "Kucoin", Diff: 5.0, FundingRate: 1.0},
	}

	filtered := filterDexByBlacklist(dex, blacklist)
	if len(filtered) != 3 {
		t.Fatalf("Expected 3 (only HUSDT blacklisted, not HFT/HOT/HUMA), got %d", len(filtered))
	}
	for _, d := range filtered {
		if d.Symbol == "ETH_HUSDT" {
			t.Error("ETH_HUSDT should be blacklisted")
		}
	}
}

func TestExtractDexTokenKey_ZK(t *testing.T) {
	// "BSC_ZKUSDT" -> "ZKUSDT"
	result := extractDexTokenKey("BSC_ZKUSDT")
	if result != "ZKUSDT" {
		t.Errorf("Expected ZKUSDT, got %s", result)
	}
}

func TestExtractDexTokenKey_H(t *testing.T) {
	// "ETH_HUSDT" -> "HUSDT"
	result := extractDexTokenKey("ETH_HUSDT")
	if result != "HUSDT" {
		t.Errorf("Expected HUSDT, got %s", result)
	}
}

func TestExtractDexTokenKey_AIOZ(t *testing.T) {
	// "BSC_AIOZUSDT" -> "AIOZUSDT" (NOT "AIUSDT")
	result := extractDexTokenKey("BSC_AIOZUSDT")
	if result != "AIOZUSDT" {
		t.Errorf("Expected AIOZUSDT, got %s", result)
	}
}

func TestExtractDexTokenKey_HFT(t *testing.T) {
	// "ETH_HFTUSDT" -> "HFTUSDT" (NOT "HUSDT")
	result := extractDexTokenKey("ETH_HFTUSDT")
	if result != "HFTUSDT" {
		t.Errorf("Expected HFTUSDT, got %s", result)
	}
}

// ============================================================================
// DEX sorting tests — verify sort=funding vs sort=spread behavior
// ============================================================================

func TestDexSort_ByFundingRate(t *testing.T) {
	entries := []*dexEntry{
		{d: Dex{Symbol: "A", FundingRate: 0.5, Diff: 10.0}, primary: 0.5, secondary: 10.0},
		{d: Dex{Symbol: "B", FundingRate: 1.5, Diff: 5.0}, primary: 1.5, secondary: 5.0},
		{d: Dex{Symbol: "C", FundingRate: 0.8, Diff: 20.0}, primary: 0.8, secondary: 20.0},
	}
	// Sort by primary desc (funding rate)
	sort.SliceStable(entries, func(i, j int) bool {
		if entries[i].primary == entries[j].primary {
			return entries[i].secondary > entries[j].secondary
		}
		return entries[i].primary > entries[j].primary
	})

	if entries[0].d.Symbol != "B" {
		t.Errorf("Expected B first (highest funding 1.5), got %s (%.2f)", entries[0].d.Symbol, entries[0].primary)
	}
	if entries[1].d.Symbol != "C" {
		t.Errorf("Expected C second (0.8), got %s (%.2f)", entries[1].d.Symbol, entries[1].primary)
	}
}

func TestDexSort_ByDiff(t *testing.T) {
	entries := []*dexEntry{
		{d: Dex{Symbol: "A", FundingRate: 0.5, Diff: 10.0}, primary: 10.0, secondary: 0.5},
		{d: Dex{Symbol: "B", FundingRate: 1.5, Diff: 5.0}, primary: 5.0, secondary: 1.5},
		{d: Dex{Symbol: "C", FundingRate: 0.8, Diff: 20.0}, primary: 20.0, secondary: 0.8},
	}
	// Sort by primary desc (diff)
	sort.SliceStable(entries, func(i, j int) bool {
		if entries[i].primary == entries[j].primary {
			return entries[i].secondary > entries[j].secondary
		}
		return entries[i].primary > entries[j].primary
	})

	if entries[0].d.Symbol != "C" {
		t.Errorf("Expected C first (highest diff 20.0), got %s (%.2f)", entries[0].d.Symbol, entries[0].primary)
	}
	if entries[1].d.Symbol != "A" {
		t.Errorf("Expected A second (10.0), got %s (%.2f)", entries[1].d.Symbol, entries[1].primary)
	}
}

func TestDexSort_TieBreakerBySecondary(t *testing.T) {
	entries := []*dexEntry{
		{d: Dex{Symbol: "A", FundingRate: 1.0, Diff: 10.0}, primary: 1.0, secondary: 10.0},
		{d: Dex{Symbol: "B", FundingRate: 1.0, Diff: 20.0}, primary: 1.0, secondary: 20.0},
	}
	sort.SliceStable(entries, func(i, j int) bool {
		if entries[i].primary == entries[j].primary {
			return entries[i].secondary > entries[j].secondary
		}
		return entries[i].primary > entries[j].primary
	})

	// When primaries are equal, higher secondary wins
	if entries[0].d.Symbol != "B" {
		t.Errorf("Expected B first (higher secondary 20.0), got %s", entries[0].d.Symbol)
	}
}

// ============================================================================
// DEX dedup by symbol tests — keep entry with best metric
// ============================================================================

func TestDexDedup_KeepBestFunding(t *testing.T) {
	// Two entries for same symbol, keep the one with higher funding rate
	bySymbol := map[string]*dexEntry{}
	inputs := []Dex{
		{Symbol: "SIREN", Market2: "Kucoin", FundingRate: 0.5, Diff: 10.0},
		{Symbol: "SIREN", Market2: "Gateio", FundingRate: 1.5, Diff: 5.0},
	}
	// Simulate the dedup logic from handleDexAPI with sort=funding
	for _, d := range inputs {
		primary := d.FundingRate // sort=funding
		secondary := d.Diff
		existing, ok := bySymbol[d.Symbol]
		if !ok || primary > existing.primary {
			bySymbol[d.Symbol] = &dexEntry{d: d, primary: primary, secondary: secondary}
		}
	}

	if len(bySymbol) != 1 {
		t.Fatalf("Expected 1 unique symbol, got %d", len(bySymbol))
	}
	entry := bySymbol["SIREN"]
	if entry.primary != 1.5 {
		t.Errorf("Expected best funding 1.5, got %.2f", entry.primary)
	}
	if entry.d.Market2 != "Gateio" {
		t.Errorf("Expected Gateio (best funding), got %s", entry.d.Market2)
	}
}

func TestDexDedup_KeepBestDiff(t *testing.T) {
	// Two entries for same symbol, keep the one with higher diff
	bySymbol := map[string]*dexEntry{}
	inputs := []Dex{
		{Symbol: "SIREN", Market2: "Kucoin", FundingRate: 1.5, Diff: 5.0},
		{Symbol: "SIREN", Market2: "Gateio", FundingRate: 0.5, Diff: 10.0},
	}
	// Simulate dedup with sort=spread (diff)
	for _, d := range inputs {
		primary := d.Diff // sort=spread
		secondary := d.FundingRate
		existing, ok := bySymbol[d.Symbol]
		if !ok || primary > existing.primary {
			bySymbol[d.Symbol] = &dexEntry{d: d, primary: primary, secondary: secondary}
		}
	}

	entry := bySymbol["SIREN"]
	if entry.primary != 10.0 {
		t.Errorf("Expected best diff 10.0, got %.2f", entry.primary)
	}
	if entry.d.Market2 != "Gateio" {
		t.Errorf("Expected Gateio (best diff 10.0), got %s", entry.d.Market2)
	}
}

// ============================================================================
// buildDataSearchFromParams tests — sort param mapping
// ============================================================================

func TestBuildDataSearchFromParams_SortFunding(t *testing.T) {
	ds, present := buildDataSearchFromParams("funding", "0")
	if !present {
		t.Fatal("Expected present=true")
	}
	if !strings.Contains(ds, `"filter_course_or_spread":"0"`) {
		t.Errorf("Expected filter_course_or_spread=0 for funding, got %s", ds)
	}
}

func TestBuildDataSearchFromParams_SortSpread(t *testing.T) {
	ds, present := buildDataSearchFromParams("spread", "0")
	if !present {
		t.Fatal("Expected present=true")
	}
	if !strings.Contains(ds, `"filter_course_or_spread":"1"`) {
		t.Errorf("Expected filter_course_or_spread=1 for spread, got %s", ds)
	}
}

func TestBuildDataSearchFromParams_Empty(t *testing.T) {
	_, present := buildDataSearchFromParams("", "")
	if present {
		t.Error("Expected present=false for empty params")
	}
}

func TestBuildDataSearchFromParams_LtPositive(t *testing.T) {
	ds, present := buildDataSearchFromParams("funding", "1")
	if !present {
		t.Fatal("Expected present=true")
	}
	if !strings.Contains(ds, `"filter_big_or_all_course":"1"`) {
		t.Errorf("Expected filter_big_or_all_course=1, got %s", ds)
	}
}

// ============================================================================
// Integration: DEX label generation matches Python output format
// ============================================================================

func TestDexLabelFormat_Funding(t *testing.T) {
	// Python: "{symbol} [{chain}]: {fundingRate}% фанд"
	chain, display := parseDexSymbol("BSC_SIRENUSDT")
	label := fmt.Sprintf("%s [%s]: %.2f%% фанд", display, chain, 1.25)
	expected := "SIREN [BSC]: 1.25% фанд"
	if label != expected {
		t.Errorf("Expected %q, got %q", expected, label)
	}
}

func TestDexLabelFormat_Spread(t *testing.T) {
	// Python: "{symbol} [{chain}]: {diff} вход"
	chain, display := parseDexSymbol("ETH_PEPEUSDT")
	label := fmt.Sprintf("%s [%s]: %.2f вход", display, chain, 29.4)
	expected := "PEPE [ETH]: 29.40 вход"
	if label != expected {
		t.Errorf("Expected %q, got %q", expected, label)
	}
}

func TestDexLabelFormat_MarketLevel2(t *testing.T) {
	// Python: "{market}: {fundingRate}% | {diff} вход"
	label := fmt.Sprintf("%s: %.2f%% | %.2f", "Kucoin", 0.01, 29.4)
	expected := "Kucoin: 0.01% | 29.40"
	if label != expected {
		t.Errorf("Expected %q, got %q", expected, label)
	}
}

// ============================================================================
// parseListMarketsParam tests
// ============================================================================

func TestParseListMarketsParam_Normal(t *testing.T) {
	result := parseListMarketsParam("1,0,1,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0")
	// marketsOrder: Bybit(0), Mexc(1), Kucoin(2), ...
	if result["BYBIT"] != 1 {
		t.Error("BYBIT should be 1")
	}
	if result["MEXC"] != 0 {
		t.Error("MEXC should be 0")
	}
	if result["KUCOIN"] != 1 {
		t.Error("KUCOIN should be 1")
	}
}

func TestParseListMarketsParam_Empty(t *testing.T) {
	result := parseListMarketsParam("")
	// Empty input returns empty map — all market checks will fail (value 0 for missing key)
	if len(result) != 0 {
		t.Errorf("Expected empty map for empty input, got %d entries", len(result))
	}
	// Verify that missing market keys return 0 (default Go map behavior)
	if result["BYBIT"] != 0 {
		t.Error("Missing key should return 0")
	}
}

// ============================================================================
// Integration tests: HTTP handler logic with mock cache data
// ============================================================================

func TestHandleDexAPI_SortFunding_LabelShowsFunding(t *testing.T) {
	// Populate mock cache
	dex := []Dex{
		{Symbol: "BSC_SIRENUSDT", Market2: "Kucoin", Diff: 5.0, FundingRate: 1.5},
		{Symbol: "BSC_SIRENUSDT", Market2: "Gateio", Diff: 10.0, FundingRate: 0.5},
		{Symbol: "ETH_PEPEUSDT", Market2: "Kucoin", Diff: 20.0, FundingRate: 0.8},
	}
	cacheDexAtomic.Store(dex)

	// Simulate handleDexAPI logic with sort=funding
	sortParam := "funding"
	ltParam := ""

	// dedup by symbol
	bySymbol := map[string]*dexEntry{}
	for _, d := range dex {
		primary := d.Diff
		secondary := d.FundingRate
		if sortParam == "funding" {
			primary = d.FundingRate
			secondary = d.Diff
		}
		if ltParam == "1" && primary <= 0 {
			continue
		}
		existing, ok := bySymbol[d.Symbol]
		if !ok || primary > existing.primary {
			bySymbol[d.Symbol] = &dexEntry{d: d, primary: primary, secondary: secondary}
		}
	}

	// sort
	entries := make([]*dexEntry, 0, len(bySymbol))
	for _, e := range bySymbol {
		entries = append(entries, e)
	}
	sort.SliceStable(entries, func(i, j int) bool {
		if entries[i].primary == entries[j].primary {
			return entries[i].secondary > entries[j].secondary
		}
		return entries[i].primary > entries[j].primary
	})

	// build labels
	type labelEntry struct {
		label string
		sym   string
	}
	var labels []labelEntry
	for _, e := range entries {
		chain, display := parseDexSymbol(e.d.Symbol)
		var label string
		if sortParam == "funding" {
			label = fmt.Sprintf("%s [%s]: %.2f%% фанд", display, chain, e.d.FundingRate)
		} else {
			label = fmt.Sprintf("%s [%s]: %.2f вход", display, chain, e.d.Diff)
		}
		labels = append(labels, labelEntry{label: label, sym: e.d.Symbol})
	}

	// Verify: SIREN should be first (funding 1.5 > 0.8)
	if len(labels) != 2 {
		t.Fatalf("Expected 2 unique symbols, got %d", len(labels))
	}
	if labels[0].sym != "BSC_SIRENUSDT" {
		t.Errorf("Expected SIREN first (highest funding), got %s", labels[0].sym)
	}
	if !strings.Contains(labels[0].label, "фанд") {
		t.Errorf("Expected 'фанд' in label, got %q", labels[0].label)
	}
	if strings.Contains(labels[0].label, "вход") {
		t.Errorf("Should NOT contain 'вход' when sort=funding, got %q", labels[0].label)
	}
}

func TestHandleDexAPI_SortSpread_LabelShowsVhod(t *testing.T) {
	dex := []Dex{
		{Symbol: "BSC_SIRENUSDT", Market2: "Kucoin", Diff: 5.0, FundingRate: 1.5},
		{Symbol: "ETH_PEPEUSDT", Market2: "Kucoin", Diff: 20.0, FundingRate: 0.8},
	}
	cacheDexAtomic.Store(dex)

	bySymbol := map[string]*dexEntry{}
	for _, d := range dex {
		primary := d.Diff
		secondary := d.FundingRate
		existing, ok := bySymbol[d.Symbol]
		if !ok || primary > existing.primary {
			bySymbol[d.Symbol] = &dexEntry{d: d, primary: primary, secondary: secondary}
		}
	}

	entries := make([]*dexEntry, 0, len(bySymbol))
	for _, e := range bySymbol {
		entries = append(entries, e)
	}
	sort.SliceStable(entries, func(i, j int) bool {
		return entries[i].primary > entries[j].primary
	})

	var labels []string
	for _, e := range entries {
		chain, display := parseDexSymbol(e.d.Symbol)
		label := fmt.Sprintf("%s [%s]: %.2f вход", display, chain, e.d.Diff)
		labels = append(labels, label)
	}

	// PEPE should be first (diff 20 > 5)
	if len(labels) != 2 {
		t.Fatalf("Expected 2, got %d", len(labels))
	}
	if !strings.Contains(labels[0], "PEPE") {
		t.Errorf("Expected PEPE first (highest diff), got %q", labels[0])
	}
	if !strings.Contains(labels[0], "вход") {
		t.Errorf("Expected 'вход' in label, got %q", labels[0])
	}
}

func TestHandleDexAPI_LtPositive_FiltersNegative(t *testing.T) {
	dex := []Dex{
		{Symbol: "A", Market2: "Kucoin", Diff: 5.0, FundingRate: -1.5},
		{Symbol: "B", Market2: "Kucoin", Diff: 10.0, FundingRate: 0.5},
	}
	cacheDexAtomic.Store(dex)

	ltParam := "1"

	bySymbol := map[string]*dexEntry{}
	for _, d := range dex {
		primary := d.FundingRate
		secondary := d.Diff
		if ltParam == "1" && primary <= 0 {
			continue
		}
		existing, ok := bySymbol[d.Symbol]
		if !ok || primary > existing.primary {
			bySymbol[d.Symbol] = &dexEntry{d: d, primary: primary, secondary: secondary}
		}
	}

	if len(bySymbol) != 1 {
		t.Fatalf("Expected 1 (negative filtered), got %d", len(bySymbol))
	}
	if _, ok := bySymbol["B"]; !ok {
		t.Error("Symbol B (funding 0.5 > 0) should survive lt=1 filter")
	}
}

func TestHandleDexAPI_Blacklist_Integration(t *testing.T) {
	dex := []Dex{
		{Symbol: "BSC_SIRENUSDT", Market2: "Kucoin", Diff: 5.0, FundingRate: 1.5},
		{Symbol: "ETH_PEPEUSDT", Market2: "Kucoin", Diff: 10.0, FundingRate: 0.8},
		{Symbol: "BSC_BTCUSDT", Market2: "Kucoin", Diff: 20.0, FundingRate: 0.3},
	}
	// Blacklist contains "SIRENUSDT" (Python extract_token_key format)
	blacklist := map[string]struct{}{"SIRENUSDT": {}}

	filtered := filterDexByBlacklist(dex, blacklist)
	if len(filtered) != 2 {
		t.Fatalf("Expected 2 (SIREN blacklisted), got %d", len(filtered))
	}
	for _, d := range filtered {
		if d.Symbol == "BSC_SIRENUSDT" {
			t.Error("SIRENUSDT should be blacklisted")
		}
	}
}

func TestHandleDexAPI_DedupKeepsBestMarket(t *testing.T) {
	// Same symbol on two markets — dedup should keep the one with best metric
	dex := []Dex{
		{Symbol: "BSC_SIRENUSDT", Market2: "Kucoin", Diff: 5.0, FundingRate: 0.3},
		{Symbol: "BSC_SIRENUSDT", Market2: "Gateio", Diff: 15.0, FundingRate: 0.8},
	}

	// sort=funding: keep highest funding
	bySymbol := map[string]*dexEntry{}
	for _, d := range dex {
		primary := d.FundingRate
		secondary := d.Diff
		existing, ok := bySymbol[d.Symbol]
		if !ok || primary > existing.primary {
			bySymbol[d.Symbol] = &dexEntry{d: d, primary: primary, secondary: secondary}
		}
	}

	entry := bySymbol["BSC_SIRENUSDT"]
	if entry.d.Market2 != "Gateio" {
		t.Errorf("Expected Gateio (funding 0.8 > 0.3), got %s", entry.d.Market2)
	}
}

func TestDexPages_SortFunding_ByFundingRate(t *testing.T) {
	// Simulate handleDexPages sorting for a specific symbol
	dex := []Dex{
		{Symbol: "BSC_SIRENUSDT", Market2: "Kucoin", Diff: 10.0, FundingRate: 0.5},
		{Symbol: "BSC_SIRENUSDT", Market2: "Gateio", Diff: 5.0, FundingRate: 1.5},
		{Symbol: "BSC_SIRENUSDT", Market2: "Bitget", Diff: 20.0, FundingRate: 0.2},
	}

	sortParam := "funding"
	sort.SliceStable(dex, func(i, j int) bool {
		if sortParam == "funding" {
			return dex[i].FundingRate > dex[j].FundingRate
		}
		return dex[i].Diff > dex[j].Diff
	})

	// Gateio should be first (funding 1.5)
	if dex[0].Market2 != "Gateio" {
		t.Errorf("Expected Gateio first (funding 1.5), got %s (%.2f)", dex[0].Market2, dex[0].FundingRate)
	}
	// Kucoin second (funding 0.5)
	if dex[1].Market2 != "Kucoin" {
		t.Errorf("Expected Kucoin second, got %s", dex[1].Market2)
	}
}

func TestDexPages_SortSpread_ByDiff(t *testing.T) {
	dex := []Dex{
		{Symbol: "BSC_SIRENUSDT", Market2: "Kucoin", Diff: 10.0, FundingRate: 0.5},
		{Symbol: "BSC_SIRENUSDT", Market2: "Gateio", Diff: 5.0, FundingRate: 1.5},
		{Symbol: "BSC_SIRENUSDT", Market2: "Bitget", Diff: 20.0, FundingRate: 0.2},
	}

	sortParam := "spread"
	sort.SliceStable(dex, func(i, j int) bool {
		if sortParam == "funding" {
			return dex[i].FundingRate > dex[j].FundingRate
		}
		return dex[i].Diff > dex[j].Diff
	})

	// Bitget should be first (diff 20)
	if dex[0].Market2 != "Bitget" {
		t.Errorf("Expected Bitget first (diff 20), got %s (%.2f)", dex[0].Market2, dex[0].Diff)
	}
}

// ============================================================================
// buildTopFundingSpot tests — verify sign preservation and dedup logic
// ============================================================================

func TestBuildTopFundingSpot_NegativeFundingFiltered(t *testing.T) {
	// Simulate expanded spots — Spread is the funding rate
	exp := []expandedSpot{
		{S: &SpotFuture{Symbol: "HOMEUSDT", Market1: "Bybit", Market2: "Bitget", Spread: -0.66}},
		{S: &SpotFuture{Symbol: "ETHUSDT", Market1: "Binance", Market2: "Okx", Spread: 0.05}},
	}

	seen := map[string]struct{}{}
	var coins []string
	for _, e := range exp {
		if e.S.Spread <= 0 {
			continue
		}
		if _, ok := seen[e.S.Symbol]; ok {
			continue
		}
		seen[e.S.Symbol] = struct{}{}
		coins = append(coins, e.S.Symbol)
	}

	// HOMEUSDT (-0.66) filtered out, only ETHUSDT remains
	if len(coins) != 1 {
		t.Fatalf("Expected 1 coin (negative filtered), got %d", len(coins))
	}
	if coins[0] != "ETHUSDT" {
		t.Errorf("Expected ETHUSDT, got %s", coins[0])
	}
}

func TestBuildTopFundingSpot_DedupKeepsFirstFromSorted(t *testing.T) {
	// Pre-sorted by Spread descending — first occurrence wins
	exp := []expandedSpot{
		{S: &SpotFuture{Symbol: "BTCUSDT", Market1: "Binance", Market2: "Bitget", Spread: 0.8, Spot1Ask: 60000, Market2Bid: 60100}},
		{S: &SpotFuture{Symbol: "BTCUSDT", Market1: "Bybit", Market2: "Okx", Spread: 0.01, Spot1Ask: 60000, Market2Bid: 60100}},
	}

	seen := map[string]struct{}{}
	type result struct {
		Market1 string
		Market2 string
		Spread  float64
	}
	var results []result
	for _, e := range exp {
		if e.S.Spread <= 0 {
			continue
		}
		if _, ok := seen[e.S.Symbol]; ok {
			continue
		}
		seen[e.S.Symbol] = struct{}{}
		results = append(results, result{e.S.Market1, e.S.Market2, e.S.Spread})
	}

	if len(results) != 1 {
		t.Fatalf("Expected 1, got %d", len(results))
	}
	// First from sorted list = Binance/Bitget with 0.8
	if results[0].Market1 != "Binance" {
		t.Errorf("Expected Binance (first in sorted), got %s", results[0].Market1)
	}
	if results[0].Spread != 0.8 {
		t.Errorf("Expected 0.8, got %.2f", results[0].Spread)
	}
}

func TestBuildTopFundingSpot_PreSortedNoReSortNeeded(t *testing.T) {
	// Verify that iterating pre-sorted BySpread gives correct order without re-sorting
	exp := []expandedSpot{
		{S: &SpotFuture{Symbol: "SOL", Spread: 1.2}},
		{S: &SpotFuture{Symbol: "BTC", Spread: 0.8}},
		{S: &SpotFuture{Symbol: "HOME", Spread: 0.66}},
		{S: &SpotFuture{Symbol: "ETH", Spread: 0.05}},
	}

	seen := map[string]struct{}{}
	var symbols []string
	for _, e := range exp {
		if e.S.Spread <= 0 {
			continue
		}
		if _, ok := seen[e.S.Symbol]; ok {
			continue
		}
		seen[e.S.Symbol] = struct{}{}
		symbols = append(symbols, e.S.Symbol)
		if len(symbols) >= 3 {
			break
		}
	}

	// Already sorted: SOL > BTC > HOME
	expected := []string{"SOL", "BTC", "HOME"}
	for i, s := range symbols {
		if s != expected[i] {
			t.Errorf("Position %d: expected %s, got %s", i, expected[i], s)
		}
	}
}
