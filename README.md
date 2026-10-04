# ChainGuard local model hosting

Run a language model on your own computer and make it available to ChainGuard. No Python installation or programming is needed for the Docker setup.

Two programs run together: **Ollama** loads the downloaded model and generates answers; the **hosting app** accepts requests in the format ChainGuard expects. Docker starts both for you. A model is a set of downloaded files, rather than a cloud API subscription.

**Current integration status:** this repository supplies the server. ChainGuard still needs its fourth provider and agent-assignment settings implemented. Starting this server does not switch ChainGuard's existing provider. The networking steps below prepare the connection; they do not add the missing provider or UI.

## First-time setup

### 1. Open Docker Desktop

Install [Docker Desktop](https://www.docker.com/products/docker-desktop/) if needed. Open it and wait until the engine is running. On Windows, use Linux containers, as with ChainGuard.

Keep this downloaded repository beside ChainGuard. E.g. directory setup:

```text
ProjectFiles/
  ChainGuard/
  ChainGuard-localLLM-template/
```

### 2. Open a terminal in the hosting folder

On Windows, open `ChainGuard-localLLM-template` in File Explorer. Click the address bar, type `powershell`, and press Enter. A terminal is a window where you enter commands. Paste each command below and press Enter.

### 3. Start the server

```powershell
docker compose up -d --build
```

The first run downloads the programs and builds the hosting app. `-d` means they continue running after you close the terminal. You still need to download a model once.

### 4. Download a model

For a small first example:

```powershell
docker compose exec ollama ollama pull llama3.2:3b
```

Wait until the download finishes. Internet access is needed for installation and downloads. Afterwards, this server generates answers locally without a cloud LLM service. ChainGuard's blockchain lookups still need internet access.

The example download is about 2 GB. Allow extra disk space and memory for Docker and the running model. No dedicated graphics card is required, although answers may be slow. This model is a setup example, not a guarantee of accurate ChainGuard analysis. Try a stronger model if it struggles with routing or evidence analysis.

### 5. Check that it works

Open **http://localhost:9010/ready** in your browser. You should see `"status":"ready"` and `llama3.2:3b` in the list. This checks that a model is installed; it does not generate an answer.

To generate an answer, open **http://localhost:9010/docs**:

1. Expand `POST /v1/chat/completions`.
2. Click **Try it out**.
3. Replace the example with the following text.
4. Click **Execute** and wait.

```json
{
  "model": "llama3.2:3b",
  "messages": [{"role": "user", "content": "Explain a blockchain in one sentence."}],
  "max_tokens": 100,
  "stream": false
}
```

The answer appears inside `choices`, then `message`, then `content`. The first answer can be slower because the model must load into memory.

## Connect ChainGuard's Docker containers

Docker gives each application its own private network. The included extra settings file connects ChainGuard's backend to the model server's network without editing ChainGuard files. It works with Docker Desktop and Linux Docker.

Keep the hosting app running. Open a terminal in the **ChainGuard** folder and run:

```powershell
docker compose -f docker-compose.yml -f ../ChainGuard-localLLM-template/chainguard-network.yaml up -d --build
```

Use the same two `-f` options for later ChainGuard commands. To stop ChainGuard:

```powershell
docker compose -f docker-compose.yml -f ../ChainGuard-localLLM-template/chainguard-network.yaml down
```

This assumes ChainGuard's backend service is called `backend`. Adjust the relative folder path if you have moved any folders elsewhere.

Once ChainGuard's local-provider settings are implemented, enter:

| Setting | Value |
| --- | --- |
| Provider | OpenAI-compatible / Local model |
| Base URL | `http://chainguard-local-llm:9010/v1` |
| Model | `llama3.2:3b` |
| API key | Leave empty unless you set one below |
| Request timeout | At least 300 seconds for the initial CPU setup |

Assign this backend to the Business Analyser, Scam Checker, and/or Forensic Investigator.

**Why two addresses?** Your browser uses `http://localhost:9010`. ChainGuard's backend uses `http://chainguard-local-llm:9010/v1` on the shared Docker network. Inside ChainGuard's container, `localhost` means ChainGuard's container itself, so it is the wrong address for this separate model server.

To check that ChainGuard can reach it, run this in the ChainGuard folder after starting both apps:

```powershell
docker compose -f docker-compose.yml -f ../ChainGuard-localLLM-template/chainguard-network.yaml exec backend python -c "import urllib.request; print(urllib.request.urlopen('http://chainguard-local-llm:9010/ready').read().decode())"
```

This checks connectivity only; it does not select a model provider.

## Everyday use

Run these commands in the hosting app folder:

| What you want | Command |
| --- | --- |
| Start again | `docker compose up -d` |
| Stop | `docker compose stop` |
| See status | `docker compose ps` |
| See errors | `docker compose logs --tail=100` |
| List installed models | `docker compose exec ollama ollama list` |
| Download another model | `docker compose exec ollama ollama pull MODEL_NAME` |

Replace `MODEL_NAME` with a name from [Ollama's library](https://ollama.com/library). Use the exact installed name in ChainGuard. Different agents can request different installed models from the same server.

Downloaded models are saved in a Docker volume. Stopping or restarting preserves them. **`docker compose down -v` deletes the saved models**, so only use it if you intend to remove them.

## Optional settings

Copy `.env.example` to a file called `.env` in this folder. Edit it with a text editor and apply changes with `docker compose up -d`.

- `LLM_TIMEOUT_SECONDS`: time allowed for generating an answer; default 300 seconds.
- `LLM_CONTEXT_TOKENS`: amount of input and output the model can work with at once; default 16384. Increasing this can use more memory. Large ChainGuard evidence bundles may need a higher value or a smaller input. Model limits still apply.
- `LLM_API_KEY`: optional password for model requests. Leave empty for the default local setup. If set, use the same value in ChainGuard; requests need an `Authorization: Bearer YOUR_KEY` header. `/ready` also requires it; `/health` stays public. The interactive documentation form does not configure this header, so use an API client for authenticated tests.

### NVIDIA graphics card acceleration

The default runs on your processor (CPU). If Docker already has access to a supported NVIDIA graphics card and your Compose version supports `gpus`, run:

```powershell
docker compose -f compose.yaml -f compose.gpu.yaml up -d --build
```

Use the same file options for later hosting commands. GPU support depends on your drivers and Docker setup; see [Ollama's Docker instructions](https://docs.ollama.com/docker). GPU configuration is optional.

## Troubleshooting

| Problem | What to do |
| --- | --- |
| Cannot connect to Docker | Open Docker Desktop and wait for its engine. |
| Port 9010 already in use | Stop the other program, or change the left-hand port in `compose.yaml`. The internal Docker address still uses 9010. |
| No models installed | Run the download command in step 4. |
| Model not found | List installed models and copy the exact name. |
| Answers take too long | Increase both the hosting and ChainGuard timeouts, or try a smaller model. |
| JSON format failed | Try a stronger model. Invalid structured answers are rejected. |
| Shared network not found | Start the hosting app before ChainGuard. |
| Browser works but ChainGuard cannot connect | Use the extra network file and Docker address, not `localhost`. |
| ChainGuard still uses a cloud provider | Its local-provider adapter and selection UI need to be implemented and selected separately. |

## API and development

This server supports `GET /v1/models` and non-streaming `POST /v1/chat/completions`. It accepts text system/user/assistant messages, temperature, max_tokens, and text/JSON-object/JSON-schema response formats. Streaming, images, tools, and other request fields are rejected. There is no automatic cloud fallback.

JSON schemas are passed to Ollama and returned JSON is validated against them. ChainGuard must still validate its agent contracts. Output stopped by the token limit returns `finish_reason: length` so ChainGuard can reject incomplete results.

`/health` checks the hosting app. `/ready` checks Ollama and downloaded models. An actual chat request checks generation. Ollama's port is not published. The app's published port is bound to `127.0.0.1`, available locally and through the shared Docker network rather than exposed to the home network.

For non-Docker development, install Python 3.12+ and run Ollama separately:

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m uvicorn app:app --host 127.0.0.1 --port 9010
```

This expects Ollama at `http://localhost:11434` unless `OLLAMA_BASE_URL` is set. The shared-network instructions apply to the recommended Docker setup.

Tests simulate Ollama without downloading a model:

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

References: [Ollama chat API](https://docs.ollama.com/api/chat), [model listing](https://docs.ollama.com/api/tags), [Docker networking](https://docs.docker.com/compose/how-tos/networking/), [example model](https://ollama.com/library/llama3.2).
