
SET FOREIGN_KEY_CHECKS = 0;


START TRANSACTION;

CREATE TABLE Users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(255) NOT NULL,
    tgid VARCHAR(255) NOT NULL,
    isSearching VARCHAR(255) NOT NULL,
    dataSearch VARCHAR(255) NOT NULL,
    listMarketsFutures TEXT NOT NULL,
    listMarketsSpot TEXT NOT NULL,
    lastNoticeCoins TEXT NOT NULL,
    blacklist TEXT NOT NULL,
    isActive VARCHAR(255) NOT NULL,
    isActiveAdmin VARCHAR(255) NOT NULL,
    timeActiveAdmin VARCHAR(255) NOT NULL,
    dataaddress TEXT NOT NULL,
    timeTest VARCHAR(255) NOT NULL,
    testActive VARCHAR(255) NOT NULL,
    referral VARCHAR(255) NOT NULL,
    information TEXT NOT NULL,
    memoAccount TEXT NOT NULL
);


CREATE TABLE Paids (
    id INT AUTO_INCREMENT PRIMARY KEY,
    txhash VARCHAR(255) NOT NULL,
    txfrom VARCHAR(255) NOT NULL,
    txvalue VARCHAR(255) NOT NULL,
    txdata TEXT NOT NULL,
    memo TEXT NOT NULL,
    inusdt VARCHAR(255) NOT NULL,
    network VARCHAR(255) NOT NULL,
    token VARCHAR(255) NOT NULL,
    txto VARCHAR(255) NOT NULL
);


CREATE TABLE Spreads (
    id INT AUTO_INCREMENT PRIMARY KEY,
    symbol VARCHAR(255) NOT NULL,
    market1 VARCHAR(255) NOT NULL,
    market2 VARCHAR(255) NOT NULL,
    market1funding FLOAT NOT NULL,
    market2funding FLOAT NOT NULL,
    market1time FLOAT NOT NULL,
    market2time FLOAT NOT NULL,
    market1bid FLOAT NOT NULL,
    market2bid FLOAT NOT NULL,
    market1fee FLOAT NOT NULL,
    market2fee FLOAT NOT NULL,
    market1predict VARCHAR(255) NOT NULL,
    market2predict VARCHAR(255) NOT NULL,
    spread FLOAT NOT NULL,
    isNew VARCHAR(255) NOT NULL,
    isUpdated VARCHAR(255) NOT NULL,
    isDeviation1 FLOAT NOT NULL,
    isDeviation2 FLOAT NOT NULL,
    market1ask FLOAT NOT NULL,
    market2ask FLOAT NOT NULL,
    m1h1 FLOAT,
    m1h3 FLOAT,
    m1h7 FLOAT,
    m1h30 FLOAT,
    m2h1 FLOAT,
    m2h3 FLOAT,
    m2h7 FLOAT,
    m2h30 FLOAT
);


CREATE TABLE SpotFutures (
    id INT AUTO_INCREMENT PRIMARY KEY,
    symbol VARCHAR(255) NOT NULL,
    market1 VARCHAR(255) NOT NULL,
    market2 VARCHAR(255) NOT NULL,
    market2funding FLOAT NOT NULL,
    market2time FLOAT NOT NULL,
    market2bid FLOAT NOT NULL,
    market1fee FLOAT NOT NULL,
    market2fee FLOAT NOT NULL,
    market2predict VARCHAR(255) NOT NULL,
    spread FLOAT NOT NULL,
    isNew VARCHAR(255) NOT NULL,
    isUpdated VARCHAR(255) NOT NULL,
    isDeviation2 FLOAT NOT NULL,
    spot1bid FLOAT NOT NULL,
    market2ask FLOAT NOT NULL,
    spot1ask FLOAT NOT NULL,
    m2h1 FLOAT,
    m2h3 FLOAT,
    m2h7 FLOAT,
    m2h30 FLOAT
);

CREATE INDEX idx_spreads_symbol ON Spreads (symbol);
CREATE INDEX idx_spreads_market1 ON Spreads (market1);
CREATE INDEX idx_spreads_market2 ON Spreads (market2);
CREATE INDEX idx_spreads_symbolSF ON SpotFutures (symbol);
CREATE INDEX idx_spreads_market1SF ON SpotFutures (market1);
CREATE INDEX idx_spreads_market2SF ON SpotFutures (market2);
CREATE INDEX idx_spreads_spread ON Spreads (spread);
CREATE INDEX idx_spreads_spreadSF ON SpotFutures (spread);


COMMIT;


SET FOREIGN_KEY_CHECKS = 1;
