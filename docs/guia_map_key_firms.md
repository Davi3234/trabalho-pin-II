# Guia rápido — Registrar a MAP_KEY da NASA FIRMS

Leva menos de 2 minutos e é gratuito. Sem essa chave o coletor (`collector/firms_collector.py`) não funciona.

1. Acesse **https://firms.modaps.eosdis.nasa.gov/api/map_key/**
2. Informe um e-mail válido (pode ser o institucional ou pessoal — a chave é enviada/exibida na própria página).
3. Copie a chave gerada (uma string alfanumérica).
4. No projeto, copie o arquivo de exemplo:
   ```
   cd collector
   cp .env.example .env
   ```
5. Abra `.env` e substitua o placeholder:
   ```
   FIRMS_MAP_KEY=sua_chave_aqui
   ```
6. Teste a coleta:
   ```
   pip install -r requirements.txt
   python firms_collector.py --region mediterraneo --days 3
   ```
   Se tudo estiver certo, um CSV com os focos de calor das últimas 72h no Mediterrâneo vai aparecer em `collector/output/`.

## Limites da API (importante para o RNF02 do escopo)

- **5.000 transações a cada 10 minutos** por MAP_KEY — mais que suficiente para uso de coleta agendada (ex.: 1x a cada 1–3h).
- Cada chamada ao endpoint de área conta como 1 transação, independente do tamanho do bounding box ou do número de focos retornados.
- Se for testar bounding boxes diferentes (Mediterrâneo, Grécia, Califórnia) em sequência durante o desenvolvimento, isso ainda está bem dentro do limite — só evite loops automáticos sem controle de frequência.

## Se preferir que eu registre por você

Como o registro pede um e-mail de contato (a NASA usa isso para avisos sobre o serviço), o ideal é que você mesmo preencha o formulário com o e-mail que quiser usar para o projeto. Se quiser, posso abrir a página no seu navegador conectado e te guiar campo a campo — é só pedir.
