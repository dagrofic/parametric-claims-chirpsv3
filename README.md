# Sistema de Regulação de Sinistros Paramétricos — CHIRPS V3.0

**Sistema profissional de regulação de sinistros paramétricos para seguros agrícolas.**

Substitui a fonte CHIRPS V2 (Google Earth Engine) por **CHIRPS V3.0** com arquivos NetCDF locais da fonte oficial CHC/UCSB.

---

## 🌐 Produção

| Ambiente | URL |
|---|---|
| Sistema Principal | https://claimsparametric.insuranceandreinsuranceapps.com/ |
| Sistema CHIRPS V3 | https://claimsparametricchirpsv3.insuranceandreinsuranceapps.com/ |
| Repositório V2 | https://github.com/dagrofic/parametric-claims-standalone |
| **Repositório V3** | **https://github.com/dagrofic/parametric-claims-chirpsv3** |

---

## 🔥 Por que CHIRPS V3?

| Característica | CHIRPS V2 | CHIRPS V3.0 |
|---|---|---|
| Latência de dados | 2-3 dias | ✅ 1-2 dias |
| Algoritmo | Original | ✅ Melhorado com correções |
| Fonte local | ❌ Google Earth Engine (API) | ✅ NetCDF local (sem API key) |
| Disponibilidade | Depende GEE | ✅ 100% autônomo |
| Formato | GEE | ✅ NetCDF padrão UCSB |

---

## ⚡ Início Rápido

### 1. Clone o repositório
```bash
git clone https://github.com/dagrofic/parametric-claims-chirpsv3.git
cd parametric-claims-chirpsv3
```

### 2. Instale as dependências
```bash
pip install -r requirements.txt
```

### 3. Baixe os dados CHIRPS V3
```bash
python scripts/download_initial_data.py
```
> ⚠️ **Atenção:** Cada arquivo anual tem ~300-500 MB. O download pode demorar vários minutos.

### 4. Inicie o servidor
```bash
python app.py
# Acesse: http://localhost:5000
```

---

## 📁 Estrutura do Projeto

```
parametric-claims-chirpsv3/
├── app.py                      # Servidor Flask principal
├── chirps_v3_extractor.py      # Extrator NetCDF (core do sistema)
├── html_parser.py              # Parser de HTML de apólices
├── requirements.txt
├── Dockerfile
├── render.yaml                 # Deploy Render.com
├── .github/
│   └── workflows/
│       └── update-chirps-data.yml  # Atualização automática (dia 15)
├── templates/
│   ├── index.html              # Interface principal
│   └── admin.html              # Painel admin / gestão de dados
├── scripts/
│   ├── download_initial_data.py    # Download inicial
│   └── start.sh                    # Script de startup
└── data/
    └── chirps_v3/
        ├── 2025/
        │   └── chirps-v3.0.rnl.2025.days_p05.nc  (baixado)
        └── 2026/
            └── chirps-v3.0.rnl.2026.days_p05.nc  (baixado)
```

---

## 🔗 Fonte de Dados CHIRPS V3

```
https://data.chc.ucsb.edu/products/CHIRPS/v3.0/daily/final/rnl/netcdf/
```

Arquivos anuais (padrão de nomenclatura):
```
chirps-v3.0.rnl.{ANO}.days_p05.nc
```

---

## 🗓 Atualização Automática

O **GitHub Actions** atualiza os dados automaticamente:
- **Quando:** Todo dia 15 de cada mês às 08:00 UTC
- **O quê:** Baixa o arquivo do ano corrente (dados do mês anterior)
- **Como:** Chama `POST /api/data/update` no sistema hospedado

Para configurar:
1. Vá em **Settings → Secrets → Actions**
2. Crie o secret `RENDER_APP_URL` com a URL do seu app no Render

---

## 🚀 Deploy no Render

### Opção A: Docker (Recomendado)
1. Crie um novo serviço Web no Render
2. Conecte ao repositório GitHub
3. Selecione **Docker** como runtime
4. Configure:
   - **Disk:** Nome `chirps-v3-data`, Mount `/data`, Size `10 GB`
   - **Env vars:** `CHIRPS_DATA_DIR=/data/chirps_v3`
5. Após o deploy, acesse `/admin` e baixe os dados

### Opção B: render.yaml (Automático)
O arquivo `render.yaml` já contém toda a configuração.
Basta conectar o repositório e o Render configura automaticamente.

---

## 📊 API Endpoints

| Método | Endpoint | Descrição |
|---|---|---|
| `GET` | `/` | Interface principal |
| `GET` | `/admin` | Painel de administração |
| `POST` | `/api/process` | Processar apólice HTML |
| `POST` | `/api/calculate` | Recalcular sinistro |
| `POST` | `/api/download-excel` | Exportar relatório Excel |
| `GET` | `/api/data/status` | Status dos arquivos CHIRPS V3 |
| `POST` | `/api/data/download` | Iniciar download de um ano |
| `POST` | `/api/data/update` | Verificar/atualizar todos |
| `GET` | `/api/task/{id}` | Status de tarefa em background |

---

## 🔬 Compatibilidade com Script Validação (Anexo 2)

O sistema reproduz **exatamente** a lógica do script de validação (`CHIRPS v3.0 script validation`):

- ✅ Detecção automática de coordenadas lat/lon/time
- ✅ Ajuste de longitude 0-360 vs -180/+180
- ✅ Extração pelo método `nearest` (pixel mais próximo)
- ✅ Cálculo Haversine de distância ponto-pixel (auditoria)
- ✅ Detecção de lacunas no período
- ✅ Fallback de engines: h5netcdf → netcdf4 → scipy
- ✅ Export Excel: dados + auditoria_arquivos + auditoria_lacunas + resumo_parametrico

---

## 📄 Licença

Uso interno — INVESTPREV SEGURADORA SA / dagrofic
