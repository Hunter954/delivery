# Delivery SaaS MVP

Plataforma SaaS multi-tenant para criação de lojas de delivery estilo iFood, com identidade visual por loja, cardápio, carrinho, checkout e painel administrativo.

## Funcionalidades

- Cadastro e login de lojista
- Criação de loja com slug (`/nativolanches`)
- Personalização visual com cores, logo e banner por URL
- Categorias e produtos
- Loja pública mobile-first
- Carrinho em sessão
- Meus pedidos no navegador (não some ao atualizar)
- Checkout mobile com ViaCEP
- QR Code Pix e copia e cola após finalizar
- SQLite persistente em /data quando DATABASE_URL não for definido
- Checkout com entrega ou retirada
- Configuração de Pix por chave ou texto
- Painel de pedidos
- Atualização de status do pedido
- Painel master simples

## Stack

- Flask
- SQLAlchemy
- Flask-Login
- Bootstrap Icons via CDN
- PostgreSQL ou SQLite

## Rodando localmente

```bash
python -m venv .venv
source .venv/bin/activate  # Linux/macOS
# ou .venv\Scripts\activate no Windows
pip install -r requirements.txt
python run.py
```

Acesse:

- Plataforma: `http://127.0.0.1:5000/`
- Admin master: `http://127.0.0.1:5000/admin`
- Demo da loja: crie sua conta e configure a loja

## Railway

### Variáveis recomendadas

- `SECRET_KEY`
- `DATABASE_URL`

Use PostgreSQL no Railway e aponte `DATABASE_URL` para ele.

## Estrutura

- `app/__init__.py` - app factory e rotas
- `app/models.py` - models do sistema
- `app/templates/` - templates
- `app/static/css/style.css` - tema visual

## Observações

Este projeto é um MVP funcional, pronto para subir no GitHub e evoluir. Para produção, as próximas melhorias recomendadas são:

- uploads reais em S3/Cloudinary
- integração Pix automática
- webhooks de pagamento
- painel de métricas
- cupons e fidelidade
- subdomínios customizados
- notificações WhatsApp
