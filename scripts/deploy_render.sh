#!/bin/bash
# ============================================================
# Deploy automático no Render.com via API
# Uso: RENDER_API_KEY=rnd_xxx bash deploy_render.sh
# ============================================================

RENDER_API_KEY="${RENDER_API_KEY:-}"
REPO_URL="https://github.com/dagrofic/parametric-claims-chirpsv3"
SERVICE_NAME="claimsparametricchirpsv3"
BRANCH="main"

if [ -z "$RENDER_API_KEY" ]; then
    echo "❌ Erro: RENDER_API_KEY não definida"
    echo "Obtenha em: https://dashboard.render.com/account/api-keys"
    echo "Uso: RENDER_API_KEY=rnd_xxx bash deploy_render.sh"
    exit 1
fi

echo "🚀 Iniciando deploy no Render.com..."
echo "Serviço: $SERVICE_NAME"
echo "Repositório: $REPO_URL"

# Verificar se serviço já existe
echo "🔍 Verificando se o serviço já existe..."
EXISTING=$(curl -s "https://api.render.com/v1/services?name=$SERVICE_NAME&limit=5" \
    -H "Authorization: Bearer $RENDER_API_KEY" \
    -H "Accept: application/json")

SERVICE_ID=$(echo "$EXISTING" | python3 -c "
import json, sys
try:
    data = json.load(sys.stdin)
    if isinstance(data, list) and len(data) > 0:
        for item in data:
            svc = item.get('service', {})
            if svc.get('name') == '$SERVICE_NAME':
                print(svc.get('id', ''))
                break
except:
    pass
" 2>/dev/null)

if [ -n "$SERVICE_ID" ]; then
    echo "✅ Serviço encontrado: $SERVICE_ID"
    echo "🔄 Disparando novo deploy..."
    RESPONSE=$(curl -s -X POST "https://api.render.com/v1/services/$SERVICE_ID/deploys" \
        -H "Authorization: Bearer $RENDER_API_KEY" \
        -H "Content-Type: application/json" \
        -d '{"clearCache": false}')
    echo "Resposta: $RESPONSE"
    echo "🎉 Deploy iniciado! Acompanhe em: https://dashboard.render.com"
else
    echo "⚠️ Serviço não encontrado. Criando via Blueprint..."
    
    # Obter owner ID
    OWNER=$(curl -s "https://api.render.com/v1/owners?limit=1" \
        -H "Authorization: Bearer $RENDER_API_KEY")
    OWNER_ID=$(echo "$OWNER" | python3 -c "
import json, sys
data = json.load(sys.stdin)
if isinstance(data, list) and len(data) > 0:
    print(data[0].get('owner', {}).get('id', ''))
" 2>/dev/null)
    
    echo "Owner ID: $OWNER_ID"
    
    # Criar serviço via render.yaml (Blueprint)
    echo "📋 Criando serviço a partir do render.yaml..."
    echo ""
    echo "INSTRUÇÃO MANUAL (necessário quando criar pela primeira vez):"
    echo "1. Acesse: https://dashboard.render.com/new/blueprint"
    echo "2. Cole a URL do repositório: $REPO_URL"
    echo "3. O Render detectará o render.yaml automaticamente"
    echo "4. Clique em 'Apply'"
    echo ""
    echo "📌 O deploy será automático em pushes futuros para branch $BRANCH"
fi
