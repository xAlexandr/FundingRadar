# Makefile
# Если файл .env существует — подключаем его
ifneq (,$(wildcard .env))
  include .env
  export
endif

COMPOSE := docker compose
COMPOSE_PROD := $(COMPOSE) -f docker-compose.yml
COMPOSE_FILES := -f docker-compose.yml -f docker-compose.dev.yml

up:
	$(COMPOSE) up
up-d:
	$(COMPOSE) up -d
dev:
	$(COMPOSE) -f docker-compose.dev.yml up --build
devr:
	$(COMPOSE) -f docker-compose.dev.yml up --force-recreate
devrd:
	$(COMPOSE) -f docker-compose.dev.yml up -d --force-recreate
devr-b:
	$(COMPOSE) -f docker-compose.dev.yml build
	$(COMPOSE) -f docker-compose.dev.yml up -d --force-recreate
udev:
	$(COMPOSE) -f docker-compose.dev.yml up
udev-d:
	$(COMPOSE) -f docker-compose.dev.yml up -d
exec:
	$(COMPOSE) exec django-app bash
build:
	$(COMPOSE) up --build
stop-funding:
	docker stop fundingradar_funding_bot_1
stop:
	$(COMPOSE) $(COMPOSE_FILES) stop
stop-prod:
	$(COMPOSE) stop
up-tgbot:
	$(COMPOSE) up -d tgbot
up-funding-bot:
	$(COMPOSE) up -d funding_bot
restart-django:
	$(COMPOSE) restart django-app
restart-tgbot:
	$(COMPOSE) restart tgbot
restart-funding-bot:
	$(COMPOSE) restart funding_bot
down:
	$(COMPOSE) down --remove-orphans
createsuperuser:
	$(COMPOSE) exec django-app python manage.py createsuperuser
makemigrations:
	$(COMPOSE) exec django-app python manage.py makemigrations
migrate:
	$(COMPOSE) exec django-app python manage.py migrate
collectstatic:
	$(COMPOSE) exec django-app python manage.py collectstatic
prod-recreate:
	$(COMPOSE) up -d --force-recreate
prod-nginx:
	$(COMPOSE) build nginx
	$(COMPOSE) up -d --no-deps --force-recreate nginx
prod-recreate-build:
	$(COMPOSE) build
	$(COMPOSE) up -d --force-recreate
prod:
	$(COMPOSE) up -d --build
clean-docker-volumes:
	docker system prune -af
clean:
	$(COMPOSE) -f docker-compose.dev.yml rm -sf
	$(COMPOSE) -f docker-compose.yml rm -sf
clean-cont-all:
	docker rm -f $$(docker ps -aq)
safe-docker-clean:
	docker image prune -f
	docker builder prune -a -f
deepclean-docker:
	docker compose down --remove-orphans
	docker image prune -a -f
	docker builder prune -a -f
logs:
	docker compose logs -f
logs-tgbot:
	docker logs -f fundingradar_tgbot_1
dump-users:
	@echo "Dumping USERS table to users_data.sql..."
	docker exec my_mysql \
	  sh -c 'exec mysqldump -u"$(MYSQL_USER)" -p"$(MYSQL_PASSWORD)" --no-create-info $(MYSQL_DATABASE) Users' \
	  > users_data.sql
	@echo "Done."

load-users:
	@echo "🗑️  Truncating Users..."
	docker exec my_mysql \
	  sh -c 'exec mysql -u"$(MYSQL_USER)" -p"$(MYSQL_PASSWORD)" -e "TRUNCATE TABLE $(MYSQL_DATABASE).Users;"'
	@echo "📥  Loading users_data.sql..."
	cat users_data.sql | docker exec -i my_mysql \
	  sh -c 'exec mysql -u"$(MYSQL_USER)" -p"$(MYSQL_PASSWORD)" $(MYSQL_DATABASE)'
	@echo "✅ Done."
update-users:
	@echo "🔄 Alter Users.columns → BLOB и заполняем b'no'..."
	@docker exec -i my_mysql sh -c '\
	  mysql -u"$(MYSQL_USER)" -p"$(MYSQL_PASSWORD)" -e "\
	    USE $(MYSQL_DATABASE); \
	    ALTER TABLE Users \
	      MODIFY COLUMN lastNoticeCoins BLOB NOT NULL, \
	      MODIFY COLUMN blacklist       BLOB NOT NULL; \
	    UPDATE Users \
	    SET \
	      lastNoticeCoins = _binary '\''no'\'', \
	      blacklist       = _binary '\''no'\''; \
	  " \
	'
	@echo "✅ done."

init-indexes:
	docker cp init_indexes.js fundingradar-mongodb-1:/init_indexes.js
	docker exec fundingradar-mongodb-1 mongosh /init_indexes.js
test-indexes-old:
	docker exec -it fundingradar-mongodb-1 mongosh
	# ВВОДИМ ЗАТЕМ ВРУЧНУЮ
	# use funding
	# db.futures.getIndexes()
add-markets-to-db:
	$(COMPOSE) exec tgbot python funding_bot/add_market_to_db.py
update-information:
	@echo "🔄 Alter Users.information → BLOB и заполняем b'no'..."
	@docker exec -i my_mysql sh -c '\
	  mysql -u"$(MYSQL_USER)" -p"$(MYSQL_PASSWORD)" -e "\
	    USE $(MYSQL_DATABASE); \
	    ALTER TABLE Users MODIFY COLUMN information BLOB NOT NULL; \
	    UPDATE Users SET information = _binary '\''no'\'' WHERE information IS NULL OR information = '\''0'\''; \
	  " \
	'
	@echo "✅ done."
update-notice:
	@echo "🔄 Alter Users.columns → BLOB и заполняем b'no'..."
	@docker exec -i my_mysql sh -c '\
	  mysql -u"$(MYSQL_USER)" -p"$(MYSQL_PASSWORD)" -e "\
	    USE $(MYSQL_DATABASE); \
	    ALTER TABLE Users \
	      MODIFY COLUMN lastNoticeCoins BLOB NOT NULL; \
	    UPDATE Users \
	    SET \
	      lastNoticeCoins = _binary '\''no'\''; \
	  " \
	'
	@echo "✅ done."
# haproxy (отдельный compose)
up-haproxy:
	$(COMPOSE) -f docker-compose.haproxy.yml up -d --build

down-haproxy:
	$(COMPOSE) -f docker-compose.haproxy.yml down

restart-haproxy:
	$(COMPOSE) -f docker-compose.haproxy.yml restart

# certbot one-off / staging / renew
certbot-issue:
	$(COMPOSE) -f docker-compose.certbot.yml run --rm certbot certonly --webroot -w /var/www/letsencrypt -d fundingradar.ru --email your-email@example.com --agree-tos --no-eff-email

certbot-issue-staging:
	$(COMPOSE) -f docker-compose.certbot.yml run --rm certbot certonly --staging --webroot -w /var/www/letsencrypt -d fundingradar.ru -d cp-bot.ru --email your-email@example.com --agree-tos --no-eff-email

certbot-renew:
	$(COMPOSE) -f docker-compose.certbot.yml run --rm certbot renew --deploy-hook "docker-compose exec nginx_proxy nginx -s reload"
