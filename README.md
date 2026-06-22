# Alterador de Metadados EXIF

Aplicativo desktop em Python/Tkinter para alterar a data e/ou o local GPS dos metadados de imagens e videos em uma pasta e suas subpastas.

## Como usar

1. Execute `iniciar_app.bat` ou rode:

   ```powershell
   python exif_metadata_app.py
   ```

2. Clique em `Buscar...` e selecione a pasta com imagens e videos.
3. Confira a tabela com o nome do arquivo, data, GPS atual e cidade identificada pelo GPS.
4. Use a coluna `Alterar` para marcar arquivos individualmente, ou selecione varias linhas com `Ctrl`/`Shift` e clique em `Marcar selecionadas`.
5. Marque `Alterar data`, `Alterar local`, ou os dois.
6. Escolha a nova data pelo botao `Calendario...`.
7. Digite a cidade e clique em `Pesquisar cidade`.
8. Clique em `Aplicar metadados na pasta`.

## Observacoes

- O app usa o ExifTool instalado em `C:\Program Files\ExifToolGUI\exiftool.exe`.
- A busca de cidade usa o servico publico Nominatim/OpenStreetMap e precisa de internet.
- O ExifTool altera os arquivos originais diretamente, sem criar backup `_original`.
- Arquivos buscados recursivamente: JPG, JPEG, TIF, TIFF, PNG, HEIC, HEIF, WEBP, MOV, MPG e MPEG.
- Em videos `.mpg` e `.mpeg`, a capacidade de escrita dos metadados pode depender do formato interno do arquivo.
