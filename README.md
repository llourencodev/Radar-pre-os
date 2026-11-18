# Radar de Preços

Buscador de preços com o mesmo visual do Radar Inteligente de Notícias. Você informa o produto e o radar consulta
Mercado Livre, KaBuM!, Pichau, Terabyte, Magalu, Amazon, Americanas, Carrefour, Ibyte, Shopee, AliExpress, o comparador Zoom e as
comunidades Pelando e Promobit. Depois disso o produto fica monitorado e é consultado de novo sozinho.

## Como executar no Windows

1. Dê dois cliques em **`iniciar.bat`**. Na primeira vez ele cria o ambiente Python (`.venv`) e instala as dependências.
2. O navegador abre em **http://localhost:8010** (porta diferente do Radar de Notícias, os dois rodam juntos).
3. Digite o produto na barra de busca, por exemplo `RTX 3060 12GB`, e clique em **Buscar preços**.

## O que aparece

- **Menor preço agora** e **preço de referência** (mediana das ofertas de produtos novos nas lojas).
- **Possível bug de preço**: oferta abaixo de 70% da referência. Abaixo de 25% vira **Suspeito** (costuma ser acessório,
  usado ou anúncio falso). Os limites ficam no `.env` (`PRECOS_BUG_RATIO`, `PRECOS_SUSPECT_RATIO`).
- **Nova oferta**: anúncio que surgiu depois da primeira busca, nas últimas 24 h. **Preço caiu**: caiu desde a coleta anterior.
- **Preço alvo**: em "Preço alvo e filtros" você define um valor; ofertas iguais ou abaixo ganham destaque.
- **Cupons**: coletados de Pelando, Cuponomia e Méliuz, ordenados pela economia estimada.
- **Histórico**: menor preço por dia do produto e histórico de cada oferta.

O filtro de relevância só aceita anúncios com todos os termos da busca e descarta variantes (`3060 Ti` quando você buscou
`3060`), acessórios, PCs completos e notebooks. Palavras extras para excluir podem ser definidas por produto.

## Site no GitHub Pages

O radar também roda sem o seu PC ligado, de graça, no GitHub, do mesmo jeito que o Radar de Notícias:

- O **GitHub Actions** (`.github/workflows/precos.yml`) roda `gerar_site.py` a cada hora. Ele consulta as lojas para os
  produtos de `config/produtos.json`, atualiza os cupons e gera um site estático na pasta `site/`. O banco
  (histórico de preços) fica guardado no cache do Actions entre as execuções.
- O site é publicado no **GitHub Pages** com a mesma interface. Painel, produtos, filtros, histórico, cupons e
  lojas funcionam no navegador, a partir de `data/precos.json`. Endereço: https://llourencodev.github.io/Radar-pre-os/
- Se nenhuma oferta for coletada, nada é publicado e o site anterior continua no ar.

**Configuração única:** no repositório, **Settings › Pages › Source: GitHub Actions**. Depois, aba **Actions** ›
**Coletar preços e publicar o site** › **Run workflow** para a primeira publicação.

**Adicionar ou remover produtos:** edite `config/produtos.json` no GitHub. Cada produto tem `query` (o que buscar),
`exclude` (palavras para descartar, separadas por vírgula) e `target_price` (preço alvo, ou `null`). Ao salvar, uma
nova coleta roda e o site é refeito em alguns minutos. Produto removido do arquivo deixa de ser coletado.
A busca do site publicado só abre produtos que já estão no arquivo.

**Segredos (opcionais):** em **Settings › Secrets and variables › Actions**, crie `TELEGRAM_BOT_TOKEN` e
`TELEGRAM_CHAT_ID` para receber os avisos e `ML_ACCESS_TOKEN` para o Mercado Livre. Eles nunca aparecem no site
nem no código. Para desligar lojas na versão online, crie a variável `PRECOS_DISABLED_STORES`.

**Atenção:** as lojas podem bloquear os servidores do GitHub com mais frequência do que bloqueiam um computador de
casa. A tela **Lojas e coleta** do site mostra o resultado de cada loja na última execução.

Para gerar o site localmente sem coletar: `.venv\Scripts\python.exe gerar_site.py --sem-coleta` (resultado em `site/`).

## Aviso no Telegram (opcional)

Preencha `TELEGRAM_BOT_TOKEN` e `TELEGRAM_CHAT_ID` no `.env` para receber bug de preço e preço alvo no celular.

## Quando uma loja falha

A tela **Lojas e coleta** mostra a situação de cada loja. Lojas mudam o site com frequência e algumas (Shopee, às vezes
Amazon e AliExpress) bloqueiam consultas automáticas. Para diagnosticar:

```
.venv\Scripts\python.exe testar_lojas.py "rtx 3060 12gb"
set PRECOS_DEBUG=1 & .venv\Scripts\python.exe testar_lojas.py "rtx 3060 12gb" kabum
```

O segundo comando guarda as páginas em `data\debug`. Lojas que não interessam podem ser desligadas em
`PRECOS_DISABLED_STORES` no `.env`.

Lojas VTEX (Carrefour, Ibyte e a Americanas) usam a API pública de busca da plataforma. Fast Shop, Casas Bahia,
Ponto, Kalunga, Patoloco, Gigantec, Mega Mamute, Inpower, Girafa e Submarino foram avaliadas e ficaram de fora.
Elas aparecem como desligadas, com o motivo, na tela **Lojas e coleta**. O radar não tenta contornar captcha nem
verificação anti-robô: loja que exige isso fica como "bloqueado".

## Mercado Livre pela API oficial (opcional)

O site do Mercado Livre costuma responder às buscas automáticas com uma verificação de conta. A API oficial
funciona com um token de acesso:

1. Entre em https://developers.mercadolivre.com.br, abra o **DevCenter** e crie um aplicativo. Use qualquer URL
   de redirecionamento que você controle, por exemplo `https://localhost/`.
2. Autorize o aplicativo com a sua conta abrindo
   `https://auth.mercadolivre.com.br/authorization?response_type=code&client_id=SEU_CLIENT_ID&redirect_uri=SUA_URL`.
   O navegador volta para a sua URL com `?code=...` no endereço.
3. Troque o código por um token:
   ```
   curl -X POST https://api.mercadolibre.com/oauth/token -d grant_type=authorization_code -d client_id=SEU_CLIENT_ID -d client_secret=SEU_SECRET -d code=CODIGO -d redirect_uri=SUA_URL
   ```
4. Copie o `access_token` da resposta para `ML_ACCESS_TOKEN` no `.env` e reinicie o radar.

O token vale 6 horas. Para renovar, use o `refresh_token` da mesma resposta com `grant_type=refresh_token`. Sem
token, ou com o token vencido, o Mercado Livre aparece como "bloqueado" com essa explicação.

Uso pessoal: o radar consulta cada loja com intervalo mínimo entre requisições e só a cada 30 minutos por produto.
