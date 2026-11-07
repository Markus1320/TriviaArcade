# TriviaArcade

An open source trivia game in the style of classic arcade cabinets: neon pixel look, CRT
scanlines, chiptune sounds. Topics are general knowledge: geography, history, science,
technology, politics, art, film, games, music, sports and more. It is played in the
browser, also on phones in the home network, in English or German.

The questions are written ahead of time. A language model writes each one from a few
connected facts of [Wikidata](https://www.wikidata.org/); a second model reviews it and
then answers it without seeing the answer, to make sure it has one clear answer. The game
itself needs no LLM: it reads the finished questions from `pool/` and checks typed
answers by code.

## Playing

Press START. Answer by typing, by picking one option, by picking every option that
applies, or by tapping items in the right order. You have 30 seconds per question.

- Each correct answer adds one to your score. The first wrong answer ends the run, unless
  you have a 1UP: you start with one, and every 3 correct answers in a row earn another
  (at most 3). A 1UP also lets you SKIP a question.
- After every answer you see a short explanation, so there is something to learn either
  way.
- After game over, save your score under a handle (3 to 8 letters or digits). The
  leaderboard shows the top 10 players with their best run.
- QUESTION LOG on the title screen lists the questions of the last games.

## Starting the game

You need [Docker Desktop](https://www.docker.com/products/docker-desktop/).

```bash
docker compose up -d --build
```

Open <http://localhost:8080>. On a phone in the same Wi-Fi, open
`http://<your PC's IP>:8080`. Settings such as the port or the time per question can be
set in a `.env` file; copy [.env.example](.env.example), which explains each one.

The game keeps players and scores in `data/game.db`. A backup is a copy of that file.

## Making new questions

That is the offline part: it needs Neo4j for the knowledge graph and an LLM (Ollama, in
the cloud or on your own PC). See "Make more questions" in
[docs/how-to.md](docs/how-to.md).

## Documentation

- [docs/how-it-works.md](docs/how-it-works.md): one question from the pool to the screen
  and back, and how a question is made. Names every file.
- [docs/how-to.md](docs/how-to.md): recipes for changing rules, texts and topics, making
  questions, backups and deploying.
- [docs/history.md](docs/history.md): what was tried and measured on the way.
- [docs/react-for-angular-devs.md](docs/react-for-angular-devs.md): the frontend, for
  Angular developers.
- [CLAUDE.md](CLAUDE.md): the rules for working on the code.

The earlier version, which wrote every question live while you played, is on the branch
`classic` (tag `v0.5.0`).

## License

MIT, see [LICENSE](LICENSE). Wikidata's data is CC0; the pixel font is under the SIL Open
Font License. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
