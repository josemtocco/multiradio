# MultiRádio WebTVs → Lista M3U (SS IPTV)

Gera automaticamente uma lista **M3U** com todas as **Web TVs** cadastradas no portal [MultiRádio](https://multiradio.com.br/webtvs.php), otimizada para o aplicativo **SS IPTV**.

## Características

- ✅ Coleta **todos** os canais listados em `https://multiradio.com.br/webtvs.php`
- ✅ Extrai nome, logo, localização (cidade/UF) e URL do stream HLS (`.m3u8`)
- ✅ **Atualização inteligente a cada 6 horas**:
  - Mantém canais que continuam ativos
  - Remove canais cujo stream ficou offline
  - Adiciona canais novos encontrados no site
- ✅ Canais agrupados por **estado (UF)** via `group-title` (ex.: `WebTVs | SP`, `WebTVs | CE`)
- ✅ Formato M3U compatível com SS IPTV (`tvg-id`, `tvg-name`, `tvg-logo`, `group-title`)
- ✅ Roda 100% no **GitHub Actions** (gratuito) + commit automático da lista

## Como usar a lista

Após o primeiro deploy, a lista ficará disponível em:

```
https://raw.githubusercontent.com/SEU_USUARIO/SEU_REPO/main/lista.m3u
```

No **SS IPTV**:

1. Abra o app → **Lista de canais** → **Adicionar lista**
2. Cole a URL acima
3. Nome sugerido: `MultiRádio WebTVs`
4. Atualize a lista sempre que quiser (o app também pode atualizar periodicamente)

## Deploy no GitHub (passo a passo)

1. Crie um repositório novo no GitHub (público ou privado).
2. Faça upload de todos os arquivos desta pasta:
   - `scrape_and_generate.py`
   - `requirements.txt`
   - `README.md`
   - `.github/workflows/update.yml`
3. (Opcional) Rode o workflow manualmente em **Actions** → **Update MultiRádio M3U** → **Run workflow**.
4. Aguarde o primeiro commit com `lista.m3u` e `channels.json`.
5. Use a URL raw da `lista.m3u` no SS IPTV.

> O workflow roda automaticamente **a cada 6 horas** (UTC) e também pode ser disparado manualmente.

## Estrutura dos arquivos

| Arquivo | Descrição |
|---------|-----------|
| `scrape_and_generate.py` | Script principal de scraping + geração do M3U |
| `channels.json` | Estado persistente (histórico de canais e status) |
| `lista.m3u` | Lista gerada pronta para o SS IPTV |
| `.github/workflows/update.yml` | Agendamento e commit automático |

## Requisitos locais (opcional)

Se quiser testar na sua máquina:

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python scrape_and_generate.py
```

## Observações

- O site atualmente lista cerca de **16 Web TVs**. O script está preparado para crescer caso novos canais sejam adicionados.
- A verificação de “canal ativo” faz um request HTTP no arquivo `.m3u8`. Streams temporariamente offline são removidos da lista até voltarem.
- Logos são extraídos do schema.org / Open Graph quando disponíveis.
- Categorias = **UF do canal** (extraída da localização publicada no site).

## Licença

Uso livre para fins pessoais e educacionais. Os streams pertencem aos respectivos canais e ao portal MultiRádio. Use com moderação e respeito aos termos de uso do site de origem.
