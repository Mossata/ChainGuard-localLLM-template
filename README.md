# ChainGuard local LLM hosting template

Run an AI language model on your computer and connect it to ChainGuard's agents. **Ollama** loads a downloaded model and generates answers. This template's **hosting service** accepts the OpenAI-compatible requests ChainGuard expects and forwards them to Ollama. Docker starts both services for you.

This is separate from the [external detector template](../ChainGuard-detector-template/README.md). A local **LLM** (large language model) generates the agents' answers; an external detector runs a separate risk-assessment algorithm. You can use both together.

Starting this server does not automatically switch ChainGuard to local AI. You must save its connection and assign it to agents in ChainGuard's settings.

## What you need

- Docker Desktop running (Linux containers on Windows), or Docker Engine with the Compose plugin on Linux.
- This complete repository and a running ChainGuard app. Follow the [main app setup guide](../ChainGuard/README.md) first; cloud AI keys are optional if all agents will use the local model.
- Internet access for initial installation/model downloads, disk space for downloaded models, and memory for Docker plus inference. CPU generation is supported but can be slow; a dedicated GPU is optional.

No separate Python installation or programming is needed for the Docker guide. Local model generation does not require a cloud AI subscription, but ChainGuard's blockchain lookups still contact external services and need their own keys where required.

An **API base URL** is the address programs use to reach the hosting service. A **model name** identifies downloaded model files and must match exactly. A **container** is an isolated process managed by Docker; `localhost` inside one refers to that container itself.

Commands use Windows PowerShell. On macOS/Linux, use `cp` instead of `Copy-Item` and `curl` instead of `curl.exe`.

## 1. Download and start the server

Keep the repository beside ChainGuard. From their parent folder:

```powershell
git clone https://github.com/Mossata/ChainGuard-localLLM-template.git
cd ChainGuard-localLLM-template
docker compose up -d --build
```

If you already have the repository, open a terminal in that folder and run only the startup command. The intended layout is:

```text
ProjectFiles/
  ChainGuard/
  ChainGuard-detector-template/   (used by ChainGuard's standard Compose setup)
  ChainGuard-localLLM-template/
```

The first run downloads Ollama and builds the hosting service. `-d` keeps them running when the terminal closes. **A model is not included yet.**

## 2. Download a model

From `ChainGuard-localLLM-template/`:

```powershell
docker compose exec ollama ollama pull llama3.2:3b
docker compose exec ollama ollama list
```

Wait for the download to finish and confirm `llama3.2:3b` appears in the list. It is a small starting example, not a guarantee of accurate blockchain analysis or valid structured answers. Try a more capable model if routing or evidence analysis fails, allowing for its memory and storage requirements.

To install another model, replace `llama3.2:3b` in the pull command with its Ollama model name. Use the exact installed name in ChainGuard. Different agents can request different installed model names through the server, although ChainGuard's current connection form selects one shared local model.

## 3. Verify readiness and generation

Open **http://localhost:9010/ready**. With the default configuration, expect `"status":"ready"` and a list containing the model.

Readiness checks that Ollama is reachable and has a model. To test actual generation:

1. Open **http://localhost:9010/docs**.
2. Expand **POST /v1/chat/completions** and click **Try it out**.
3. Replace the request with the JSON below.
4. Click **Execute** and wait for the answer in `choices[0].message.content`.

```json
{
  "model": "llama3.2:3b",
  "messages": [
    {"role": "user", "content": "Explain a blockchain in one sentence."}
  ],
  "max_tokens": 100,
  "stream": false
}
```

The first request may take longer while the model loads. `/health` only checks that the hosting process is alive; it does not check Ollama or generate an answer.

## 4. Connect ChainGuard

### If ChainGuard runs in Docker

Start this hosting stack first so its shared network exists. Then, from `ChainGuard/`:

```powershell
docker compose -f docker-compose.yml -f ../ChainGuard-localLLM-template/chainguard-network.yaml up -d --build
```

The second file connects ChainGuard's backend to the hosting network. Use the same two `-f` options for later ChainGuard commands, including `up`, `ps`, `logs`, and `down`. This does not replace ChainGuard's normal detector-repository requirement.

### Enter the connection details

Sign in to ChainGuard as **admin**. The supplied ChainGuard Docker setup uses username `admin` and password `ChainGuard123!`; native installations use the account values set in their backend terminal.

Open **Settings > Local LLM Connection**:

| Field | Value |
| --- | --- |
| Connection name | `My local Llama`, or another descriptive name |
| API base URL | Choose from the table below; include `/v1` |
| Model name | `llama3.2:3b`, or the exact name from `ollama list` |
| Optional API key | Leave empty with this template's defaults |
| Timeout (seconds) | `300` to start with |

| Setup | Base URL seen by ChainGuard's backend |
| --- | --- |
| Both stacks in Docker, connected using the override above | `http://chainguard-local-llm:9010/v1` |
| Native ChainGuard, hosting stack in Docker on the same computer | `http://localhost:9010/v1` |
| Both services running natively on the same computer | `http://localhost:9010/v1` |
| Docker ChainGuard, hosting service running directly on the host | `http://host.docker.internal:9010/v1` (server must accept Docker connections) |

Do not use `/docs`, `/ready`, or `/v1/chat/completions` as the base URL.

Click **Test Connection**, turn on **Enable local LLM**, then click **Save Connection**. Saving an enabled connection checks the installed model and generates a small structured JSON answer. A failed check leaves the previous saved settings intact.

### Assign the agents

Open **Settings > AI Configuration**, choose **Local Hosted LLM** for the Business Analyser, Scam Checker, and Forensic Investigator, then click **Save Agent Providers**. You can mix local and cloud providers if the cloud keys are configured. Settings affect future messages for all users; a running response keeps its original settings.

Ask **"What is a smart contract?"** to test the connection through ChainGuard. Then try an Ethereum address lookup with a configured Etherscan key. To exercise the local **Scam Checker**, disable the external detector under **Settings > External Detector**, save, and confirm. With an external detector enabled, that service handles scam assessments instead; the AI agents still interpret requests and explain evidence as applicable.

There is no automatic fallback to a cloud model when local generation fails. A successful connection test does not guarantee every later model response will meet ChainGuard's schemas or be accurate.

## Optional server settings

From this template folder:

```powershell
Copy-Item .env.example .env
```

Edit the new `.env` file and apply changes with `docker compose up -d`.

| Variable | Default | Purpose |
| --- | --- | --- |
| `LLM_API_KEY` | Empty | Optional bearer secret for `/ready` and `/v1/*`. Enter the same value in ChainGuard's Optional API key field. |
| `LLM_TIMEOUT_SECONDS` | `300` | How long the hosting service waits for Ollama. Increase ChainGuard's connection timeout too when allowing slower generation. |
| `LLM_CONTEXT_TOKENS` | `16384` | Context window requested from Ollama: space for input and output tokens. Increasing it can use more memory; model limits still apply. |

A **token** is a unit of model text. Large evidence bundles may need more context space, while output token limits independently cap generated answers. Raising the context window does not make a model more accurate.

Keys remain on the server and in local configuration files. Do not commit `.env` with secrets. This bearer key is separate from Etherscan keys, cloud AI keys, and `DETECTOR_API_KEY`.

### Test with authentication enabled

When `LLM_API_KEY` is set, opening `/ready` directly in a browser returns 401 because it has no authorization header. Test with:

```powershell
curl.exe http://localhost:9010/ready -H "Authorization: Bearer YOUR_SECRET"
```

Replace `YOUR_SECRET` with your configured value. `/health` remains public. The interactive `/docs` form does not configure this bearer header; use an API client for authenticated generation tests or ChainGuard's connection test.

### Optional NVIDIA GPU acceleration

If Docker already has access to a supported NVIDIA GPU and your Compose version supports `gpus`, start the template with:

```powershell
docker compose -f compose.yaml -f compose.gpu.yaml up -d --build
```

Use the same two file options for later commands **in this template folder**. These differ from the two files used for ChainGuard's shared-network connection. GPU drivers and Docker GPU access must be configured separately; the default CPU setup needs no GPU override.

## Stop, restart, and update

From `ChainGuard-localLLM-template/` (include the GPU override if using it):

```powershell
docker compose ps
docker compose logs --tail 100 llm ollama
docker compose down
docker compose up -d
docker compose up -d --build
```

These commands show service status, show logs, stop the stack, start it again, and rebuild/start after hosting code or dependency changes. Models are saved in the `models` Docker volume and survive normal stops/restarts. **`docker compose down -v` deletes that stack's saved models.** Download another model with `ollama pull`; restarting alone does not install one.

ChainGuard stores its enabled connection and agent assignments separately in its own settings file/data volume. Stopping this hosting stack leaves those assignments selected, so local AI requests fail until it is restarted or you change providers.

## Troubleshooting

| Problem | What to check |
| --- | --- |
| Cannot connect to Docker | Start Docker Desktop and wait for its engine. |
| Port 9010 in use | Stop the other process or change the left-hand published port in `compose.yaml`. The internal shared-network URL still uses 9010. |
| `/ready` reports no models | Run `docker compose exec ollama ollama pull llama3.2:3b` and wait. |
| Model not found | Run `docker compose exec ollama ollama list` and copy the exact name into ChainGuard. |
| `/health` works but `/ready` fails | Inspect Ollama logs and installed models; liveness alone does not establish readiness. |
| 401 | Match `LLM_API_KEY` with ChainGuard's saved key or the client's bearer header. |
| Shared network not found | Start this template before starting ChainGuard with its override. |
| Browser connects but ChainGuard cannot | Use the backend-visible URL and shared-network file; `localhost` inside Docker points to the caller's container. |
| Generation too slow / 504 | Try a smaller model, optional GPU acceleration, or longer timeouts on both sides. |
| Invalid JSON / schema mismatch | Try a more capable model; malformed structured output is rejected. |
| Local option unavailable / cloud still used | Enable and save the connection, then assign Local Hosted LLM to the desired agents and save. |
| Scam Checker appears unused | An enabled external detector handles scam assessment; disable it to use the built-in AI assessment. |

## Testing and native development

The Docker guide is the supported first-time path. For development without Docker, install Python 3.12 and run Ollama separately on the same computer with a model already downloaded. From this repository:

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m uvicorn app:app --host 127.0.0.1 --port 9010
```

The default Ollama URL is `http://localhost:11434`. Set `OLLAMA_BASE_URL` in the server terminal before startup if needed. Native runs do not automatically load `.env`; set `LLM_API_KEY`, timeout, and context variables in that terminal too. PowerShell uses `$env:NAME = "value"`; macOS/Linux uses `export NAME='value'` and `.venv/bin/python`.

Tests simulate Ollama, so no downloaded model or live server is required:

```powershell
.venv\Scripts\python -m pip install -r requirements-dev.txt
.venv\Scripts\python -m pytest -q
```

Use readiness, a generation request, and a ChainGuard chat to verify an actual deployment; mocked tests do not validate a model's analysis quality.

## Architecture and API reference

```text
ChainGuard backend -> hosting service (:9010) -> Ollama -> downloaded model
                       OpenAI-compatible        /api/chat
                       /v1 endpoints            /api/tags
```

`compose.yaml` starts `llm` and `ollama`, persists model files, and creates the `chainguard-local-llm-shared` network. The hosting service's shared alias is `chainguard-local-llm`. Only port 9010 is published, bound to `127.0.0.1`; Ollama's port is not published. This is a local setup, not a complete public hosting configuration.

| Route | Behavior |
| --- | --- |
| `GET /health` | Hosting process liveness; always public. |
| `GET /ready` | Checks Ollama and requires at least one installed model. |
| `GET /v1/models` | OpenAI-compatible installed model list. |
| `POST /v1/chat/completions` | Non-streaming text generation. |
| `GET /docs` | Interactive request documentation. |

Chat requests accept `model`, text `messages` with system/user/assistant roles, `temperature`, `max_tokens`, `stream: false`, and `response_format` (`text`, `json_object`, or `json_schema`). Streaming, images, tools, and unsupported request fields are rejected. This is a limited compatibility layer, not the full OpenAI API.

JSON schemas are passed to Ollama and returned JSON is validated when generation completes normally. Output stopped by the token limit returns `finish_reason: length`; the caller must handle incomplete answers. ChainGuard also validates its own agent contracts. Request errors return 400, authentication failures 401, missing models 404, unavailable Ollama 503, timeouts 504, and other upstream/invalid-output failures 502.
