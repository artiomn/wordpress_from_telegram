# Telegram to Wordpress converter

Script to import posts from Telegram exported JSON to Wordpress


## How to export data from TG

Use "Export" button in PC client.


## How to run

```
./wordpress_from_telegram/tg_to_wp.py --app-key 'Mine APpl Word Pres sKeY DaTa' --skip-existing-posts --unite-empty-messages --use-ai "https://www.optimamechanica.ru"
```


## Parameters

```
➭ ./tg_to_wp.py --help
usage: tg_to_wp.py [-h] [--user USER] [--app-key APP_KEY] [--use-ai] [--skip-existing-posts] [--maximum-posts-count MAXIMUM_POSTS_COUNT] [--tg-result-file TG_RESULT_FILE] [--unite-empty-messages] wp_host

Telegram to WordPress importer

positional arguments:
  wp_host               WordPress host

options:
  -h, --help            show this help message and exit
  --user USER           User login
  --app-key APP_KEY     Application key
  --use-ai              Use AI to create title
  --skip-existing-posts
                        Don't add post if it already exists (only titles compared)
  --maximum-posts-count MAXIMUM_POSTS_COUNT
                        Maximum posts count to publish
  --tg-result-file TG_RESULT_FILE
                        File exported from Telegram
  --unite-empty-messages
                        Unite TG messages without text
```
