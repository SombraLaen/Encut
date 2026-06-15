# Log de alteracoes

﻿# Log de alteracoes

ï»¿# Log de alteracoes

Ã¯Â»Â¿# Log de alteracoes

## v1.1.39 - 2026-06-15
- Instalador passa a baixar um runtime Python portatil completo pela release do GitHub.
- A instalacao valida `python.exe`, `pythonw.exe` e `tkinter` antes de prosseguir.
- O instalador oficial da Python.org ficou apenas como fallback, com log proprio e sem varredura ampla em `Program Files`.

## v1.1.38 - 2026-06-15
- Corrigida a instalacao local do Python em maquinas onde o instalador oficial ignora o `TargetDir`.
- O instalador agora limpa instalacoes parciais, passa `DefaultJustForMeTargetDir` e copia o Python encontrado para `runtime\python` quando necessario.

## v1.1.36 - 2026-06-15
- Sistema de atualizacao migrado para GitHub Releases.
- `update_config.json` agora aponta para o repositorio `SombraLaen/Encut`.
- Se nao houver release, a verificacao usa `VERSION` e `EncutSetup.exe` do branch configurado.
- A verificacao continua aceitando manifesto `update.json` como fallback.
- O instalador tambem consulta o GitHub antes de prosseguir com a instalacao.

## v1.1.1 - 2026-05-16
- Versao atualizada para 1.1.1.
- Mudancas:
  - versao removida do cabecalho e do status da UI;
  - versao mantida no titulo da janela e no log inicial de processamento;
  - controle automatico de versao por hash dos arquivos principais;
  - registro automatico de mudancas em CHANGELOG.md.

## v1.1.2 - 2026-05-16T16:00:19
- Versao atualizada automaticamente de 1.1.1 para 1.1.2.
- Resumo: adicionados icones `?` com explicacoes por hover em cada opcao da interface.
- Mudancas detectadas:
  - silence_cutter.py
  - README.md

## v1.1.3 - 2026-05-16T16:05:40
- Versao atualizada automaticamente de 1.1.2 para 1.1.3.
- Resumo: implementado sistema de presets para salvar, carregar e excluir ajustes de corte/exportacao.
- Mudancas detectadas:
  - silence_cutter.py
  - README.md

## v1.1.4 - 2026-05-16T16:06:19
- Versao atualizada automaticamente de 1.1.3 para 1.1.4.
- Mudancas detectadas:
  - silence_cutter.py

## v1.1.5 - 2026-05-16T16:16:57
- Versao atualizada automaticamente de 1.1.4 para 1.1.5.
- Resumo: chamadas internas de ffmpeg/ffprobe agora rodam ocultas no Windows para evitar janelas de CMD durante o processamento.
- Mudancas detectadas:
  - silence_cutter.py
  - README.md
  - iniciar.bat

## v1.1.6 - 2026-05-16T16:21:19
- Versao atualizada automaticamente de 1.1.5 para 1.1.6.
- Resumo: todos os relatorios agora usam a pasta central `C:\Users\Sombra\Desktop\codex\relatorios`.
- Mudancas detectadas:
  - silence_cutter.py
  - README.md

## v1.1.7 - 2026-05-16T16:41:06
- Versao atualizada automaticamente de 1.1.6 para 1.1.7.
- Resumo: adicionado detector de fala como modo padrao para cortes mais precisos, com alternativa de silencio tradicional.
- Mudancas detectadas:
  - silence_cutter.py
  - README.md

## v1.1.8 - 2026-05-16T16:41:42
- Versao atualizada automaticamente de 1.1.7 para 1.1.8.
- Resumo: documentacao ajustada para o novo modo de deteccao por fala e presets com deteccao.
- Mudancas detectadas:
  - README.md

## v1.1.9 - 2026-05-16T17:41:25
- Versao atualizada automaticamente de 1.1.8 para 1.1.9.
- Resumo: relatorios agora sao salvos em subpastas individuais, mantendo o TXT e o JSON da mesma execucao juntos.
- Mudancas detectadas:
  - silence_cutter.py
  - README.md

## v1.1.10 - 2026-05-18T00:26:10
- Versao atualizada automaticamente de 1.1.9 para 1.1.10.
- Resumo: adicionada opcao de intervalos protegidos para impedir cortes dentro de trechos informados pelo usuario.
- Mudancas detectadas:
  - silence_cutter.py
  - README.md

## v1.1.11 - 2026-05-18T00:43:51
- Versao atualizada automaticamente de 1.1.10 para 1.1.11.
- Resumo: melhorado o tratamento de falhas do ffmpeg, com log completo em `relatorios\erros_ffmpeg`, resumo de erro mais claro na tela e ajustes de timestamps/fila de mux para reduzir falhas na conversao final.
- Mudancas detectadas:
  - silence_cutter.py
  - README.md

## v1.1.12 - 2026-05-18T01:04:04
- Versao atualizada automaticamente de 1.1.11 para 1.1.12.
- Resumo: adicionado instalador e desinstalador locais para Windows, com atalhos, registro em Aplicativos instalados, manifesto e logs na pasta `instalacao`.
- Mudancas detectadas:
  - silence_cutter.py
  - README.md
  - instalar.bat
  - desinstalar.bat
  - instalar.ps1
  - desinstalar.ps1

## v1.1.13 - 2026-05-18T01:04:46
- Versao atualizada automaticamente de 1.1.12 para 1.1.13.
- Resumo: ajustado o manifesto do instalador para registrar somente atalhos realmente criados e melhorar a mensagem do modo de simulacao.
- Mudancas detectadas:
  - instalar.ps1

## v1.1.14 - 2026-05-18T01:15:56
- Versao atualizada automaticamente de 1.1.13 para 1.1.14.
- Resumo: iniciado o instalador executavel unico, com launcher preparado para usar Python e ffmpeg locais em `runtime`.
- Mudancas detectadas:
  - silence_cutter.py
  - README.md
  - iniciar.bat
  - instalar.bat
  - desinstalar.bat
  - launcher/Iniciar.cs
  - launcher/Iniciar.csproj
  - installer/CortadorSilencioSetup.csproj
  - installer/Program.cs

## v1.1.15 - 2026-05-18T01:18:42
- Versao atualizada automaticamente de 1.1.14 para 1.1.15.
- Resumo: instalador ajustado para compilar como `.exe` unico pelo .NET Framework, embutindo os arquivos da ferramenta e baixando Python/ffmpeg automaticamente.
- Mudancas detectadas:
  - launcher/Iniciar.csproj
  - installer/CortadorSilencioSetup.csproj
  - installer/Program.cs

## v1.1.16 - 2026-05-18T01:19:38
- Versao atualizada automaticamente de 1.1.15 para 1.1.16.
- Resumo: documentacao atualizada para explicar que o setup baixa dependencias automaticamente e que Python/ffmpeg manuais sao apenas alternativa.
- Mudancas detectadas:
  - README.md

## v1.1.17 - 2026-05-18T01:29:17
- Versao atualizada automaticamente de 1.1.16 para 1.1.17.
- Resumo: ferramenta renomeada para Encut, com titulo da janela, launcher, instalador, atalhos, registro do Windows e pasta padrao migrados para o novo nome.
- Mudancas detectadas:
  - silence_cutter.py
  - README.md
  - instalar.bat
  - desinstalar.bat
  - instalar.ps1
  - desinstalar.ps1
  - launcher/Iniciar.cs
  - installer/EncutSetup.csproj
  - installer/Program.cs
  - installer/CortadorSilencioSetup.csproj removido

## v1.1.18 - 2026-05-18T01:37:37
- Versao atualizada automaticamente de 1.1.17 para 1.1.18.
- Resumo: setup agora exibe a versao do Encut no cabecalho de ajuda, no log de instalacao/desinstalacao e na mensagem final de instalacao.
- Mudancas detectadas:
  - installer/Program.cs

## v1.1.19 - 2026-05-18T01:54:19
- Versao atualizada automaticamente de 1.1.18 para 1.1.19.
- Mudancas detectadas:
  - silence_cutter.py

## v1.1.20 - 2026-05-18T01:54:49
- Versao atualizada automaticamente de 1.1.19 para 1.1.20.
- Mudancas detectadas:
  - silence_cutter.py

## v1.1.21 - 2026-05-18T01:56:06
- Versao atualizada automaticamente de 1.1.20 para 1.1.21.
- Mudancas detectadas:
  - silence_cutter.py

## v1.1.22 - 2026-05-18T01:57:00
- Versao atualizada automaticamente de 1.1.21 para 1.1.22.
- Mudancas detectadas:
  - silence_cutter.py

## v1.1.23 - 2026-05-18T01:59:51
- Versao atualizada automaticamente de 1.1.22 para 1.1.23.
- Resumo: adicionado sistema de autoatualizacao por update.json hospedado em site, botao Atualizar, opcoes CLI de atualizacao e script para gerar pacote ZIP de distribuicao.
- Mudancas detectadas:
  - README.md
  - installer/EncutSetup.csproj
  - installer/Program.cs

## v1.1.24 - 2026-05-18T02:01:38
- Versao atualizada automaticamente de 1.1.23 para 1.1.24.
- Mudancas detectadas:
  - silence_cutter.py

## v1.1.25 - 2026-05-18T02:02:00
- Versao atualizada automaticamente de 1.1.24 para 1.1.25.
- Resumo: corrigida a verificacao de atualizacao para carregar urllib/zipfile e aceitar update.json UTF-8 com BOM gerado no Windows.
- Mudancas detectadas:
  - silence_cutter.py

## v1.1.26 - 2026-05-18T02:31:01
- Versao atualizada automaticamente de 1.1.25 para 1.1.26.
- Mudancas detectadas:
  - installer/Program.cs

## v1.1.27 - 2026-05-18T12:31:47
- Versao atualizada automaticamente de 1.1.26 para 1.1.27.
- Mudancas detectadas:
  - installer/Program.cs

## v1.1.28 - 2026-05-19T02:14:49
- Versao atualizada automaticamente de 1.1.27 para 1.1.28.
- Mudancas detectadas:
  - silence_cutter.py

## v1.1.29 - 2026-05-19T02:19:41
- Versao atualizada automaticamente de 1.1.28 para 1.1.29.
- Mudancas detectadas:
  - silence_cutter.py
  - installer/Program.cs

## v1.1.30 - 2026-05-19T02:21:13
- Versao atualizada automaticamente de 1.1.29 para 1.1.30.
- Mudancas detectadas:
  - silence_cutter.py

## v1.1.31 - 2026-05-19T02:21:46
- Versao atualizada automaticamente de 1.1.30 para 1.1.31.
- Mudancas detectadas:
  - silence_cutter.py

## v1.1.32 - 2026-05-19T18:04:03
- Versao atualizada automaticamente de 1.1.31 para 1.1.32.
- Mudancas detectadas:
  - silence_cutter.py
  - installer/Program.cs

## v1.1.33 - 2026-05-19T21:51:03
- Versao atualizada automaticamente de 1.1.32 para 1.1.33.
- Mudancas detectadas:
  - silence_cutter.py
  - installer/Program.cs

## v1.1.34 - 2026-05-19T21:51:34
- Versao atualizada automaticamente de 1.1.33 para 1.1.34.
- Mudancas detectadas:
  - installer/Program.cs

## v1.1.35 - 2026-05-19T22:20:49
- Versao atualizada automaticamente de 1.1.34 para 1.1.35.
- Mudancas detectadas:
  - silence_cutter.py
  - README.md

## v1.1.37 - 2026-06-14T22:59:56
- Versao atualizada automaticamente de 1.1.36 para 1.1.37.
- Mudancas detectadas:
  - silence_cutter.py
  - README.md
  - installer/Program.cs

## v1.1.40 - 2026-06-14T23:43:34
- Versao atualizada automaticamente de 1.1.39 para 1.1.40.
- Mudancas detectadas:
  - silence_cutter.py
  - installer/Program.cs

## v1.1.41 - 2026-06-14T23:56:44
- Versao atualizada automaticamente de 1.1.40 para 1.1.41.
- Mudancas detectadas:
  - installer/Program.cs

## v1.1.42 - 2026-06-15T05:30:24
- Versao atualizada automaticamente de 1.1.41 para 1.1.42.
- Mudancas detectadas:
  - installer/Program.cs

## v1.1.43 - 2026-06-15T05:42:41
- Versao atualizada automaticamente de 1.1.42 para 1.1.43.
- Mudancas detectadas:
  - silence_cutter.py

