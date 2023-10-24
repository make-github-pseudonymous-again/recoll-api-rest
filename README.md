`recoll-api-rest`
==

> :phone: A REST API to communicate with the
> [`recoll`](https://www.lesbonscomptes.com/recoll) database.


## `build`

The image exposes the HTTP API on port `80` and expects
read-only access to a recoll index at `/index`.

```sh
docker build -t recoll-api-rest:latest .
```

## `run`

A `compose.yaml` file allows to easily configure and run the docker
image with `RECOLL_CONFDIR` and `PORT`.

```sh
env RECOLL_CONFDIR="$HOME/.recoll" PORT=8080 docker compose up -d
```

## `stop`

```sh
env RECOLL_CONFDIR="$HOME/.recoll" PORT=8080 docker compose down
```
