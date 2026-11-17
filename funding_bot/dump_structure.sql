-- MySQL dump 10.13  Distrib 8.0.42, for Linux (x86_64)
--
-- Host: localhost    Database: funding
-- ------------------------------------------------------
-- Server version	8.0.42-0ubuntu0.24.04.2

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!50503 SET NAMES utf8mb4 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;

--
-- Table structure for table `Paids`
--

DROP TABLE IF EXISTS `Paids`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `Paids` (
  `id` int NOT NULL AUTO_INCREMENT,
  `txhash` varchar(255) NOT NULL,
  `txfrom` varchar(255) NOT NULL,
  `txvalue` varchar(255) NOT NULL,
  `txdata` text NOT NULL,
  `memo` text NOT NULL,
  `inusdt` varchar(255) NOT NULL,
  `network` varchar(255) NOT NULL,
  `token` varchar(255) NOT NULL,
  `txto` varchar(255) NOT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `SpotFutures`
--

DROP TABLE IF EXISTS `SpotFutures`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `SpotFutures` (
  `id` int NOT NULL AUTO_INCREMENT,
  `symbol` varchar(255) NOT NULL,
  `market1` varchar(255) NOT NULL,
  `market2` varchar(255) NOT NULL,
  `market2funding` float NOT NULL,
  `market2time` float NOT NULL,
  `market2bid` float NOT NULL,
  `market1fee` float NOT NULL,
  `market2fee` float NOT NULL,
  `market2predict` varchar(255) DEFAULT NULL,
  `spread` float NOT NULL,
  `isNew` varchar(255) NOT NULL,
  `isUpdated` varchar(255) NOT NULL,
  `isDeviation2` float NOT NULL,
  `spot1bid` float NOT NULL,
  `market2ask` float NOT NULL,
  `spot1ask` float NOT NULL,
  `m2h1` float DEFAULT NULL,
  `m2h3` float DEFAULT NULL,
  `m2h7` float DEFAULT NULL,
  `m2h30` float DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `idx_unique_spot_futures` (`symbol`,`market1`,`market2`),
  KEY `idx_spreads_spreadSF` (`spread`)
) ENGINE=InnoDB AUTO_INCREMENT=5018746 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `Spreads`
--

DROP TABLE IF EXISTS `Spreads`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `Spreads` (
  `id` int NOT NULL AUTO_INCREMENT,
  `symbol` varchar(255) NOT NULL,
  `market1` varchar(255) NOT NULL,
  `market2` varchar(255) NOT NULL,
  `market1funding` float NOT NULL,
  `market2funding` float NOT NULL,
  `market1time` float NOT NULL,
  `market2time` float NOT NULL,
  `market1bid` float NOT NULL,
  `market2bid` float NOT NULL,
  `market1fee` float NOT NULL,
  `market2fee` float NOT NULL,
  `market1predict` varchar(255) DEFAULT NULL,
  `market2predict` varchar(255) DEFAULT NULL,
  `spread` float NOT NULL,
  `isNew` varchar(255) NOT NULL,
  `isUpdated` varchar(255) NOT NULL,
  `isDeviation1` float NOT NULL,
  `isDeviation2` float NOT NULL,
  `market1ask` float NOT NULL,
  `market2ask` float NOT NULL,
  `m1h1` float DEFAULT NULL,
  `m1h3` float DEFAULT NULL,
  `m1h7` float DEFAULT NULL,
  `m1h30` float DEFAULT NULL,
  `m2h1` float DEFAULT NULL,
  `m2h3` float DEFAULT NULL,
  `m2h7` float DEFAULT NULL,
  `m2h30` float DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `idx_unique_spreads` (`symbol`,`market1`,`market2`),
  KEY `idx_spreads_spread` (`spread`)
) ENGINE=InnoDB AUTO_INCREMENT=4265768 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `Users`
--

DROP TABLE IF EXISTS `Users`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `Users` (
  `id` int NOT NULL AUTO_INCREMENT,
  `username` varchar(255) NOT NULL,
  `tgid` varchar(255) NOT NULL,
  `isSearching` varchar(255) NOT NULL,
  `dataSearch` varchar(255) NOT NULL,
  `listMarketsFutures` text NOT NULL,
  `listMarketsSpot` text NOT NULL,
  `lastNoticeCoins` text NOT NULL,
  `blacklist` text NOT NULL,
  `isActive` varchar(255) NOT NULL,
  `isActiveAdmin` varchar(255) NOT NULL,
  `timeActiveAdmin` varchar(255) NOT NULL,
  `dataaddress` text NOT NULL,
  `timeTest` varchar(255) NOT NULL,
  `testActive` varchar(255) NOT NULL,
  `referral` varchar(255) NOT NULL,
  `information` text NOT NULL,
  `memoAccount` text NOT NULL,
  PRIMARY KEY (`id`)
) ENGINE=InnoDB AUTO_INCREMENT=2 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `futures`
--

DROP TABLE IF EXISTS `futures`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `futures` (
  `id` int NOT NULL AUTO_INCREMENT,
  `exchange_name` varchar(255) NOT NULL,
  `symbol` varchar(255) NOT NULL,
  `datetime` datetime NOT NULL,
  `ask` float NOT NULL,
  `bid` float NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `exchange_name` (`exchange_name`,`symbol`,`datetime`)
) ENGINE=InnoDB AUTO_INCREMENT=136146 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `spot`
--

DROP TABLE IF EXISTS `spot`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `spot` (
  `id` int NOT NULL AUTO_INCREMENT,
  `exchange_name` varchar(255) NOT NULL,
  `symbol` varchar(255) NOT NULL,
  `datetime` datetime NOT NULL,
  `ask` float NOT NULL,
  `bid` float NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `exchange_name` (`exchange_name`,`symbol`,`datetime`)
) ENGINE=InnoDB AUTO_INCREMENT=408271 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

-- Dump completed on 2025-08-01  9:48:59
