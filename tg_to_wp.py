#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import logging
from wp_api import WPClient
from wp_api.auth import ApplicationPasswordAuth, BasicAuth
from pathlib import Path
import json
import re


class WordPressImporter:
    def __init__(self, wp_url: str, user: str, password: str, skip_existing: bool = True):
        """
        :skip_existing skip posts if title is already exists in WP.
        """
        self._skip_existing = skip_existing
        self._media_items = dict()
        self._existing_posts = []
        self._client = self._make_wordpress_client(wp_url, user, password)
        self._cached_tags = dict()

        if skip_existing:
            # Filenames after TG export are unique
            self._media_items = {Path(mi['guid']['rendered']).name: mi for mi in self._client.media.list()}
            self._existing_posts = [(post['title']['rendered'], post['content']['rendered'])
                                    for post in self._client.posts.list(status=['publish', 'draft'])]

    @property
    def tags(self):
        if not self._cached_tags:
            self._cached_tags = {tag['id']: tag['name'] for tag in self._client.tags.list()}

        return self._cached_tags

    def add_tags(self, tags: list[str]):
        old_tags = self.tags.values()
        for tag in tags:
            if tag not in old_tags:
                try:
                    self._client.tags.create(name=tag)
                except Exception as e:
                    logging.warning(e)

                self._cached_tags = dict()

    def upload_file(self, filename: Path):
        if self._skip_existing and filename.name in self._media_items.keys():
            return self._media_items[filename.name]

        # Upload a new image.
        with open(filename, 'rb') as file_to_upload:
            media = self._client.media.upload(
                file_to_upload,
                file_name=filename.name
                # title=title,
                # alt_text='Description of my image'
            )

            return media

    def upload_post(self, title: str, text: str, tags: set[str] | None = None, post_type: str = 'draft') -> bool:
        """
        :post_type can be: publish, future, draft, pending, private.
        """

        if self._skip_existing:
            # Get all published posts.
            for e_title, e_text in self._existing_posts:
                if e_title == title: # and e_text == text:
                    logging.info(f'Skipping post "%s"...', title)
                    return False

        if tags is not None:
            self.add_tags(tags)
            tags_ids = [tag[0] for tag in self.tags.items() if tag[1] in tags]
        else:
            tags_ids = None

        logging.info(f'Creating post "%s"...', title)
        # Create a new post
        new_post = self._client.posts.create(
            title=title,
            content=text,
            status=post_type,
            tags=tags_ids
        )

        return True

    @staticmethod
    def _make_wordpress_client(wp_url: str, user: str, password: str) -> WPClient:
        # Initialize client with Application Password authentication
        auth = ApplicationPasswordAuth(username=user, app_password=password)
        # auth = BasicAuth(username=user, password=password)
        client = WPClient(base_url=wp_url, auth=auth) #auth is optional

        return client


class TGProcessor:
    """
    Read exported from TG JSON file and craft messages from photos, files, etc.
    """

    def __init__(self):
        self._tags = set()

    @property
    def tags(self) -> dict(int, str):
        return enumerate(self.tags)

    def _process_text(self, te: dict[str: str]) -> tuple[str, set[str]]:
        text = ''
        te_type = te['type']
        tags = set()

        if 'plain' == te_type:
            text = te['text']
        elif 'bold' == te_type:
            text = f'<b>{te["text"]}</b>'
        elif 'italic' == te_type:
            text = f'<i>{te["text"]}</i>'
        elif 'underline' == te_type:
            text = f'<u>{te["text"]}</u>'
        elif 'strikethrough' == te_type:
            text = f'<s>{te["text"]}</s>'
        elif 'pre' == te_type:
            text = f'<pre>{te["text"]}</pre>'
        elif 'link' == te_type:
            text = f'<a href="{te["text"]}">{te["text"]}</a>'
        elif 'text_link' == te_type:
            text = f'<a href="{te["href"]}">{te["text"]}</a>'
        elif 'hashtag' == te_type:
            tag = te['text'].replace('#', '')
            self._tags.add(tag)
            tags.add(tag)
        else:
            text = te['text']

        return re.sub(r'\n', '<br>\n', text), tags

    def load_messages(self, path_to_json, unite_messages_without_text: bool = True):
        logging.info('Processing "%s"', path_to_json)
        with open(path_to_json, 'rt', encoding='utf-8') as msg_dump:
            result = {
                'tags': set(),
                'text': '',
                'date': None,
                'files': []
            }

            for message in json.load(msg_dump)['messages']:
                # print(json.dumps(message, indent=2, ensure_ascii=False).encode('utf-8').decode(), '\n=====')
                if message['text']:  # text is not empty.
                    if result['text'] or result['files']:
                        yield result

                    result_text = []
                    result_tags = set()
                    for te in message['text_entities']:
                        text, tags = self._process_text(te)
                        result_text.append(text)
                        result_tags = result_tags.union(tags)

                    files = []
                    check_words = ('photo', 'file')
                    for cw in check_words:
                        if cw  in message.keys():
                            f_to_add = {
                                cw: message[cw]
                            }

                            add_keys = ('mime_type', 'media_type')
                            for k in add_keys:
                                if k in message.keys():
                                    f_to_add[k] = message[k]

                            files.append(f_to_add)

                    # New result.
                    result = {
                        'tags': result_tags,
                        'text': ''.join(result_text),
                        'date': message['date'],
                        'files': files
                    }

                elif unite_messages_without_text:
                    if 'photo' in message.keys() or 'file' in message.keys():
                        result['files'].append(message)

            if result['text'] or result['files']:
                yield result
        logging.info('Processing "%s" finished.', path_to_json)


class AITitleGetter:
    def __init__(self):
        # Optional requirement.
        from g4f.client import Client
        self._client = Client()

    def __call__(self, text: str) -> str:
        response = self._client.chat.completions.create(
            model='',
            # stream=False,
            messages=[{'role': 'user',
                       'content': 'Make title from text. '
                       'Print only plain titles in text language no more 10 words length'
                       'Make titles without line breaks and special characters.'},
                      {'role': 'user', 'content': text}]
        )

        return re.sub('<.*>', '', response.choices[0].message.content)


def simple_title_getter(text: str) -> str:
    for line in text.split('\n'):
        line = re.sub('<.*>', '', line)
        if len(line) > 2:
            return line

    return 'no title'


class HybridTitleGetter:
    def __init__(self):
        self._ai_getter = AITitleGetter()

    def __call__(self, text: str):
        try:
            return self._ai_getter(text)
        except Exception as e:
            logging.warning(e)
            return simple_title_getter(text)


def post_tg_messages_to_wp(tg_processor, wp_importer, result_filename, title_getter,
                           max_posts_count: int = -1, unite_empty: bool = True):
    posts_count = 0

    for msg in tg_processor.load_messages(result_filename, unite_empty):
        if max_posts_count > 0 and posts_count >= max_posts_count:
            break

        add_text = []
        for media_file in msg['files']:
            file_path = Path(media_file.get('file', media_file.get('photo')))
            logging.info(f'Uploading file "%s"...', file_path.name)
            uploaded_data = wp_importer.upload_file(file_path)
            tl_data = uploaded_data['description']['rendered']
            add_text.append(f'{tl_data}\n')

        new_text = f'{"\n".join(add_text)}\n{msg["text"]}' if add_text else msg['text']
        if wp_importer.upload_post(title_getter(msg['text']), new_text, tags=msg['tags']):
            # Skipped posts don't counted.
            posts_count += 1


if '__main__' == __name__:
    parser = argparse.ArgumentParser(description='Telegram to WordPress importer')
    parser.add_argument('wp_host', default='https://www.optimamechanica.com', help='WordPress host')
    parser.add_argument('--user', default='admin', help='User login')
    parser.add_argument('--app-key', default='', help='Application key')
    parser.add_argument('--use-ai', action='store_true', help='Use AI to create title')
    parser.add_argument('--skip-existing-posts', action='store_true',
                        help='Don\'t add post if it already exists (only titles compared)')
    parser.add_argument('--maximum-posts-count', type=int, default=-1, help='Maximum posts count to publish')
    parser.add_argument('--tg-result-file', default='result.json', help='File exported from Telegram')
    parser.add_argument('--unite-empty-messages', action='store_true', help='Unite TG messages without text')

    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    title_getter = HybridTitleGetter() if args.use_ai else simple_title_getter

    tg_proc = TGProcessor()
    wp_importer = WordPressImporter(args.wp_host, args.user, args.app_key, skip_existing=args.skip_existing_posts)

    post_tg_messages_to_wp(tg_proc, wp_importer, args.tg_result_file, title_getter,
                           args.maximum_posts_count, args.unite_empty_messages)

