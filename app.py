import json
import logging
import os
import random
import time

from flask import Flask, request
from slack_bolt import App
from slack_bolt.adapter.flask import SlackRequestHandler
from slack_sdk import WebClient

from poker.structures import leagues

import poker.db as db
import poker.engine as engine

logging.basicConfig(level=logging.DEBUG)

token = os.environ.get("SLACK_BOT_TOKEN")
channel = os.environ.get("SLACK_CHANNEL")

app = Flask(__name__, static_url_path='/static')
bolt = App()
handler = SlackRequestHandler(bolt)

slack = WebClient(token=token)

@app.route("/bolt", methods=["POST"])
def slack_events():
    return handler.handle(request)

@app.route("/")
def index():
    return {}

@bolt.command("/game")
def poker_cmd(ack, respond, command, logger):
    ack()

    user = command['user_id']
    cmd  = command['text'] if 'text' in command else ''
    pieces = cmd.split()

    if len(pieces) != 1:
        respond(response_type="ephemeral", text="Which league do you want to play in? Try something like `/poker [{"|".join(leagues.keys())}]`")
        return

    league_in = pieces[0]
    buyin     = pieces[1]

    league = None

    for name, data in leagues.items():
        if league_in == name or league_in in data['synonyms']:
            league = name
            break

    if league is None:
        respond(response_type="ephemeral", text=f"I don't know this '{league_in}' you speak of. Try one of these: " + ", ".join(set(leagues.keys())))
        return

    buyin = data['buyin']
    units = data['units']

    response = slack.chat_postMessage(channel=channel, text=f"<@{user}> wants to play {league} poker 💪. The buy-in is {buyin} {units}. Who's in?")

    game_id = f"{response['channel']}-{response['ts']}"

    logger.info(f"Initializing a game: {game_id}")

    state = {
      'host': user,
      'league': league,
      'buyin': int(buyin),
      'status': 'pending',
      'players': [user],
    }

    conn = db.get_conn()
    db.save_game(conn, game_id, state)
    conn.commit()
    conn.close()

@bolt.event('reaction_added')
def handle_reaction(event, logger):
    logger.info(event)

    if event['item']['type'] != 'message':
        return

    game_id = f"{event['item']['channel']}-{event['item']['ts']}"

    engine.maybe_add_player(slack, game_id, event['user'], logger)

@bolt.action("fold")
def handle_fold_action(ack, respond, body, logger):
    ack()

    respond(delete_original=True)

    engine.fold(slack, body['user']['id'], body['user']['name'], json.loads(body['actions'][0]['value']))

@bolt.action("check")
def handle_check_action(ack, respond, body, logger):
    ack()

    respond(delete_original=True)

    engine.check(slack, body['user']['id'], body['user']['name'], json.loads(body['actions'][0]['value']), logger)

@bolt.action("raise")
def handle_raise_action(ack, respond, body, logger):
    ack()

    respond(delete_original=True)

    engine.single(slack, body['user']['id'], body['user']['name'], json.loads(body['actions'][0]['value']))

@bolt.action("double")
def handle_double_action(ack, respond, body, logger):
    ack()

    respond(delete_original=True)

    engine.double(slack, body['user']['id'], body['user']['name'], json.loads(body['actions'][0]['value']))
