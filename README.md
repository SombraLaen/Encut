# Encut

Ferramenta local em Python que usa `ffmpeg` para detectar e remover trechos de silencio em videos longos.

Antes de cortar, ela analisa quantas faixas de audio existem no video. Se houver duas ou mais, as faixas sao mescladas em uma unica trilha para a deteccao de silencio e para o arquivo final.

Por padrao, a deteccao usa o modo `Fala precisa`: o audio e filtrado para a faixa principal da voz, analisado em blocos curtos e convertido em trechos de fala. Isso tende a cortar melhor com ruido de fundo, respiracoes e pausas curtas do que a deteccao simples de silencio.

O modo `Video Use` integra transcripts JSON compativeis com [browser-use/video-use](https://github.com/browser-use/video-use) e ElevenLabs Scribe. Quando um transcript com timestamps por palavra e informado, o Encut monta os trechos mantidos por limite de palavra, gera `takes_packed.md` e exporta um EDL JSON compativel junto do relatorio.

Durante o processamento, o log mostra tempo decorrido e estimativa restante. No final, ele mostra:

- duracao e tamanho do video original;
- duracao e tamanho do video final;
- tempo reduzido;
- diferenca de tamanho;
- tempo total decorrido.

Ao finalizar, a ferramenta salva todos os relatorios na pasta central `C:\Users\Sombra\Desktop\Encut\relatorios`:

- cada execucao cria uma subpasta propria dentro de `relatorios`;
- dentro dessa subpasta ficam juntos o relatorio `.txt` legivel e o `.json` estruturado;
- no modo lote, o relatorio consolidado tambem fica em uma subpasta propria.

Controle de versao local:

- se o arquivo de saida ja existir, a versao anterior e movida automaticamente para `backups`;
- cada relatorio registra a versao da ferramenta e o caminho do backup criado;
- a versao da ferramenta aparece apenas no titulo da janela, no log de inicio do processamento e nos relatorios;
- a cada alteracao dos arquivos principais, a versao patch e atualizada automaticamente;
- as mudancas detectadas ficam registradas em `CHANGELOG.md`;
- a pasta central `relatorios` tambem mantem `historico_versoes.json` com o historico das execucoes.

## Requisitos

- Internet na primeira instalacao pelo `EncutSetup.exe`, para baixar Python e ffmpeg automaticamente.
- Em instalacao manual, Python 3.11 ou superior e `ffmpeg.exe`.

Se o `ffmpeg` nao estiver no PATH, baixe o build para Windows e selecione o `ffmpeg.exe` dentro da propria interface.

## Como abrir

Clique duas vezes em `iniciar.exe`, ou rode:

```powershell
python silence_cutter.py --gui
```

O arquivo `iniciar.bat` foi mantido apenas como alternativa simples.

As chamadas internas ao `ffmpeg` e `ffprobe` rodam ocultas no Windows para evitar janelas de CMD abrindo e fechando durante o processamento.

Se o `ffmpeg` falhar, a ferramenta salva o log completo em `relatorios\erros_ffmpeg` e mostra na tela um resumo com a causa mais provavel. Os arquivos temporarios de corte sao criados na propria pasta de saida para reduzir falhas por falta de espaco no temp do Windows.

## Instalar e desinstalar

Para instalar no Windows, clique duas vezes em `EncutSetup.exe`.

O instalador e um unico `.exe`, nao precisa de administrador e mantem a aplicacao dentro desta pasta `Encut`. Ele baixa automaticamente as dependencias para `runtime`:

- Python local, com suporte a Tkinter para a interface;
- ffmpeg e ffprobe locais.

Depois disso, ele cria:

- atalho na area de trabalho;
- pasta no Menu Iniciar;
- atalho de desinstalacao no Menu Iniciar;
- entrada em Aplicativos instalados do Windows para o usuario atual;
- manifesto e logs em `instalacao`.

O arquivo `instalar.bat` foi mantido apenas como alternativa e chama o instalador `.exe` quando ele existe.

Para desinstalar, use o atalho `Desinstalar Encut` no Menu Iniciar, a lista de aplicativos do Windows ou clique em `desinstalar.bat`.

O desinstalador pergunta se voce quer manter os arquivos ou apagar tudo. Mantendo os arquivos, ele remove atalhos e registro do Windows, mas preserva a pasta `Encut`, relatorios, backups, presets e runtime. Apagando tudo, ele remove a pasta inteira da ferramenta.

Tambem e possivel rodar diretamente:

```powershell
.\EncutSetup.exe /uninstall
```

## Atualizacao automatica

O Encut pode verificar novas versoes em um site. Para isso, hospede os arquivos gerados em `dist_site` e configure `update_config.json`:

```json
{
  "enabled": true,
  "check_on_startup": true,
  "manifest_url": "https://seu-site.com/encut/update.json"
}
```

O arquivo `update.json` do site informa a versao mais recente, o pacote `.zip` e o hash SHA256. O campo `zip_url` pode ser relativo ao proprio `update.json` ou uma URL completa.

Na interface, use o botao `Atualizar`. Pela linha de comando:

```powershell
python silence_cutter.py --check-update --update-manifest "https://seu-site.com/encut/update.json"
python silence_cutter.py --install-update --update-manifest "https://seu-site.com/encut/update.json"
```

Para gerar o pacote do site:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\build_site_package.ps1
```

Esse comando cria `dist_site\update.json`, `dist_site\Encut_VERSAO.zip` e `dist_site\Encut_site_upload_VERSAO.zip`.
Na interface, o botao de entrada permite selecionar um ou varios videos. Com varios videos, a saida passa a ser uma pasta, e cada arquivo recebe o sufixo `_sem_silencio`.

Cada opcao da interface tem um icone `?`. Passe o mouse sobre ele para ver exatamente o que aquela opcao faz e como ela afeta os cortes.

Presets:

- use `Salvar` para gravar os ajustes atuais com um nome;
- use `Carregar` para aplicar um preset salvo;
- use `Excluir` para remover um preset;
- presets ficam em `presets_ajustes.json` e salvam apenas os ajustes de corte, deteccao e exportacao, sem caminhos de videos.

## Ajustes principais

- `Silencio abaixo de (dB)`: quanto menor, mais permissivo. Comece com `-35`.
- `Silencio minimo (s)`: duracao minima para considerar um trecho como silencio.
- `Margem antes/depois (s)`: preserva um pouco de audio ao redor dos cortes.
- `Ignorar cortes`: protege intervalos do video contra cortes internos, por exemplo `01:30-03:00; 05:10 ate 06:00`.
- `Transcript Video Use`: opcional; informe o JSON de transcricao ou uma pasta de transcripts no modo lote.
- `Deteccao`: `Fala precisa` identifica trechos com voz; `Video Use` usa timestamps por palavra de um transcript; `Silencio tradicional` usa o silencedetect do ffmpeg.
- `Modo preciso`: recodifica e corta no ponto correto.
- `Modo rapido`: copia o video, mas pode cortar perto dos keyframes. Se houver mais de uma faixa de audio, o audio ainda sera recodificado para permitir a mescla.

## Linha de comando

Um video:

```powershell
python silence_cutter.py "entrada.mp4" "saida.mp4" --detection-mode speech --threshold -35 --min-silence 0.45 --padding 0.12
```

Proteger um trecho contra cortes:

```powershell
python silence_cutter.py "entrada.mp4" "saida.mp4" --ignore-ranges "01:30-03:00;05:10-06:00"
```

Varios videos:

```powershell
python silence_cutter.py --batch --output-dir "saida" "video1.mp4" "video2.mp4" "video3.mp4"
```

Se `--output-dir` nao for informado, a ferramenta cria uma pasta `sem_silencio` ao lado do primeiro video.

Usar um transcript do Video Use/Scribe para cortes por palavra:

```powershell
python silence_cutter.py "entrada.mp4" "saida.mp4" --detection-mode video_use --video-use-transcript "edit\transcripts\entrada.json"
```

No modo lote, `--video-use-transcript` pode apontar para uma pasta com um JSON para cada video, usando o mesmo nome base do arquivo.

Para voltar ao comportamento antigo de corte por silencio:

```powershell
python silence_cutter.py "entrada.mp4" "saida.mp4" --detection-mode silence
```

