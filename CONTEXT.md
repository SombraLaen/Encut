# Encut Domain Glossary

## Core Concepts

### Video Processing

| Term | Definition |
|------|------------|
| **Silêncio** | Segmento de áudio com volume abaixo do limiar configurado (dB) por duração mínima |
| **Fala** | Segmento de áudio que contém voz humana detectada |
| **Trecho** | Contínuo de vídeo com início e fim definidos (Segment) |
| **Padding** | Margem de áudio preservada antes e depois de cada trecho mantido |
| **Lote** | Processamento de múltiplos vídeos em sequência |

### Detection Modes

| Term | Definition |
|------|------------|
| **Fala precisa** | Detecção por análise de energia RMS com filtro de faixa vocal (90-7500Hz) |
| **Silêncio tradicional** | Detecção via filtro `silencedetect` do ffmpeg |
| **Video Use** | Detecção baseada em timestamps de palavras de um transcript JSON |

### Export Modes

| Term | Definition |
|------|------------|
| **Modo preciso** | Recodifica vídeo e áudio (libx264 + aac), cortes exatos |
| **Modo rápido** | Copia streams quando possível, cortes próximos a keyframes |

### Configuration

| Term | Definition |
|------|------------|
| **Preset** | Combinação nomeada de ajustes de corte (dB, duração mínima, padding, etc.) |
| **Ignorar cortes** | Intervalos protegidos que não podem ser removidos |
| **Transcript** | JSON com timestamps por palavra (browser-use/video-use ou ElevenLabs Scribe) |

### UI Terms

| Term | Definition |
|------|------------|
| **Log** | Painel de saída com mensagens coloridas do processamento |
| **Info do vídeo** | Painel com duração, tamanho e faixas de áudio do vídeo selecionado |
