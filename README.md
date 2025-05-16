# MSC_Project_LightBulb

Inicialização ACME:
docker run -it -p 8080:8080 --name acme-onem2m-cse ankraft/acme-onem2m-cse

Requirements:
Python
Instalar biblioteca requests <pip install requests>

Tasks:

Fazer um pedido ao ACME para registar a lâmpada (check)

Colocar a lampada a escutar do ACME para fazer a alteração de estado

## Requirements

Python 3.12 to latest version (older versions of 3.x will also work)

## Development

### Clone the repo

### Initialze virtual enviroment (optional)

```sh
python -m venv .venv
```
Windows (cmd.exe)
```sh
.venv/Scripts/activate.bat
```
Windows (PowerShell)
```sh
.venv/Scripts/Activate.ps1
```
Linux/MacOS
```sh
source .venv/bin/activate
```

### Install dependencies

```sh
pip install -r requirements.txt
```


