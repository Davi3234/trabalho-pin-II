# Prompt — Integrar o IGNIS com a Oracle Cloud Free

> Cole este arquivo inteiro no Claude Desktop. Responda as perguntas da seção "Decisões em aberto" antes dele começar.

## Seu papel

Você vai me guiar, passo a passo, para colocar o projeto IGNIS no ar na **Oracle Cloud Free Tier (Always Free)**. Eu executo os passos no console da Oracle e no terminal. Você explica o que clicar e o que digitar, e me ajuda a diagnosticar erros quando eu colar a saída. Dê um passo por vez e espere minha confirmação antes do próximo. Não presuma que já tenho conta, VM ou chave SSH.

## O projeto

IGNIS é um DSS de monitoramento de incêndios florestais (disciplina 75PIN, UDESC). Repositório: `trabalho-pin-II`.

- `backend/`: pacote Python único (FastAPI + SQLAlchemy/GeoAlchemy2 + Alembic + APScheduler).
  - `ignis.api`: API FastAPI, porta 8000. Aplica as migrations e o seed das regiões ao iniciar.
  - `ignis.worker`: coletor agendado (NASA FIRMS + FWI/EFFIS). Roda um ciclo ao subir e depois a cada `COLLECT_INTERVAL_MINUTES` (padrão 60).
- `frontend/`: React + Vite + react-leaflet + Recharts. Em dev, o Vite faz proxy de `/api` para `127.0.0.1:8000`. Também lê arquivos estáticos em `public/data/*.json`.
- `infra/docker-compose.yml`: PostGIS 16 (`postgis/postgis:16-3.4`), API e worker. **Ainda não há serviço de frontend/Nginx.**
- `.env.example` na raiz: precisa de `POSTGRES_PASSWORD` e `FIRMS_MAP_KEY` (veja `docs/guia_map_key_firms.md`).

Subir a stack hoje:

```
docker compose -f infra/docker-compose.yml --env-file .env up -d --build
```

## Objetivo

1. O **coletor (worker) roda sozinho**, 24h por dia, na Oracle Cloud.
2. O **frontend abre** por um endereço público. O professor só precisa ver o frontend.

## Arquitetura proposta (palpite, pode ser contestado)

- Uma **VM Always Free** (preferência: Ampere A1 / ARM, Ubuntu) rodando o compose existente.
- **Serviço Nginx novo** no compose: serve o build estático do React e repassa `/api` para a API.
- Só o Nginx (porta 80, depois 443) fica exposto à internet. Banco e API continuam em `127.0.0.1`/rede interna.
- Acesso inicial por `http://IP-PUBLICO`. HTTPS só se eu tiver um domínio.

## Decisões em aberto (pergunte-me)

1. O professor deve ver **dados reais acumulados pelo coletor via API** (padrão que assumo) ou os **dados estáticos/modo demo** do front?
2. Tenho um domínio para usar com HTTPS?
3. Já tenho conta Oracle Cloud? (O cadastro exige cartão para verificação; o Always Free não deve cobrar.)

## Pontos de atenção que você deve checar comigo

- **Imagem ARM:** confirme se `postgis/postgis:16-3.4` tem build `linux/arm64`. Se não tiver, proponha alternativa (imagem comunitária com arm64, ou build próprio) antes de eu subir qualquer coisa. Verifique em vez de presumir.
- **Capacidade Ampere A1:** a região pode estar sem capacidade. Explique o que fazer se der "Out of host capacity" (tentar outro AD, tentar mais tarde) e a alternativa AMD Micro (1 GB de RAM, apertada para PostGIS + API + worker).
- **Rede em duas camadas:** liberar as portas 80/443 na Security List/NSG da VCN **e** no firewall da própria VM (no Ubuntu da Oracle, regras `iptables` padrão bloqueiam; instrua a abrir 80/443 de forma persistente).
- **Recuperação de VMs ociosas:** a Oracle pode reclamar instâncias Always Free com uso muito baixo. Comente se isso afeta um worker que roda a cada hora e o que fazer.
- **Segredos:** `.env` fica só na VM, nunca no Git. Confira que `POSTGRES_PASSWORD` e `FIRMS_MAP_KEY` não vão para o repositório.
- **Persistência:** o volume `pgdata` precisa sobreviver a reinícios; e `restart: unless-stopped` já está nos serviços.
- **Backfill opcional:** `docker compose ... run --rm worker python -m ignis.worker --backfill 90` carrega histórico (cerca de 20 transações por dia da FIRMS).

## Roteiro esperado (ajuste se discordar)

1. Criar/conferir conta Oracle Cloud e escolher a home region.
2. Criar a VM Always Free e a chave SSH; anotar o IP público.
3. Abrir as portas na VCN e no firewall da VM.
4. Instalar Docker + Compose plugin; clonar o repositório.
5. Criar o `.env` na VM.
6. Adicionar ao repositório o serviço Nginx e o build do frontend ao compose (me peça os arquivos atuais; eu cole aqui antes de você propor mudanças).
7. Subir a stack, validar `/health`, o worker nos logs e o frontend no navegador.
8. (Opcional) domínio + HTTPS com Let's Encrypt.

## Como quero que você trabalhe

- Português, direto, um passo por vez.
- Quando faltar informação sobre o código, **peça o arquivo** em vez de adivinhar.
- Antes de qualquer comando destrutivo (apagar volume, recriar banco), avise e peça confirmação.
- No final de cada etapa, diga como eu verifico que funcionou.
