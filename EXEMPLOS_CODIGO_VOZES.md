# 💻 Exemplos de Código - Sistema de Vozes

## 📚 Índice
1. [Importações](#importações)
2. [Gerenciamento de Vozes](#gerenciamento-de-vozes)
3. [Planos](#planos)
4. [Validações](#validações)
5. [Casos de Uso](#casos-de-uso)

---

## Importações

```python
from app import omni_voices as voices_mgr
from app.repositories import user_voices, voice_plans
from app.models.user_voice import UserVoice
from app.models.voice_plan import VoicePlan
from app.database import SessionLocal
```

---

## Gerenciamento de Vozes

### Listar Vozes do Usuário

```python
from app import omni_voices as voices_mgr

# Listar todas as vozes de um usuário
user_id = 1
voices = voices_mgr.list_custom(user_id)

# Resultado: lista de dicts
# [
#   {
#     "id": "abc123",
#     "name": "Voz Masculina",
#     "filename": "omni_u1_voz_masculina_abc123.wav",
#     "reference_text": "Este é um exemplo de texto"
#   }
# ]

print(f"Usuário {user_id} tem {len(voices)} vozes")
for voice in voices:
    print(f"- {voice['name']} (ID: {voice['id']})")
```

### Criar Nova Voz

```python
from app import omni_voices as voices_mgr

# Dados da voz
user_id = 1
name = "Minha Nova Voz"
reference_text = "Texto de exemplo para clonagem"

# Ler arquivo de áudio
with open("audio.wav", "rb") as f:
    audio_bytes = f.read()

# Obter informações do plano do usuário
from app.repositories import users as users_repo
user = users_repo.get_user_by_id(user_id)
plan = user.get("voice_plan", {})
max_voices = plan.get("max_voices", 10) if plan else 10
is_unlimited = plan.get("is_unlimited", False) if plan else False

# Criar voz
try:
    voice = voices_mgr.save_custom(
        user_id=user_id,
        name=name,
        content=audio_bytes,
        original_filename="audio.wav",
        reference_text=reference_text,
        max_voices=max_voices,
        is_unlimited=is_unlimited,
    )
    print(f"✅ Voz criada: {voice['name']} (ID: {voice['id']})")
except ValueError as e:
    print(f"❌ Erro: {e}")
    # Exemplo de erro: "Limite de 10 vozes atingido para este plano."
```

### Obter Informações de Uma Voz

```python
from app import omni_voices as voices_mgr

voice_id = "abc123"
user_id = 1

# Obter voz (com verificação de propriedade)
voice = voices_mgr.get_custom(voice_id, user_id)

if voice:
    print(f"Nome: {voice['name']}")
    print(f"Arquivo: {voice['filename']}")
    print(f"Texto de referência: {voice['reference_text']}")
else:
    print("Voz não encontrada ou sem permissão")
```

### Deletar Voz

```python
from app import omni_voices as voices_mgr

voice_id = "abc123"
user_id = 1

# Deletar voz (soft delete)
success = voices_mgr.delete_custom(voice_id, user_id)

if success:
    print("✅ Voz deletada com sucesso")
else:
    print("❌ Voz não encontrada ou sem permissão")
```

---

## Planos

### Obter Plano de um Usuário

```python
from app.repositories import users as users_repo

user_id = 1
user = users_repo.get_user_by_id(user_id)

if user and user.get("voice_plan"):
    plan = user["voice_plan"]
    print(f"Plano: {plan['name']}")
    print(f"Limite: {plan['max_voices'] if not plan['is_unlimited'] else 'Ilimitado'}")
    print(f"É ilimitado: {plan['is_unlimited']}")
else:
    print("Usuário sem plano atribuído")
```

### Listar Todos os Planos

```python
from app.repositories import voice_plans

# Listar apenas planos ativos
plans = voice_plans.get_all_plans(active_only=True)

for plan in plans:
    print(f"{plan['name']}: {plan['max_voices']} vozes (ilimitado: {plan['is_unlimited']})")

# Resultado:
# Plano Básico: 10 vozes (ilimitado: False)
# Plano Admin: 0 vozes (ilimitado: True)
```

### Obter Plano Específico

```python
from app.repositories import voice_plans

# Obter plano básico
basic_plan = voice_plans.get_basic_plan()
print(f"Plano básico: {basic_plan['name']} - {basic_plan['max_voices']} vozes")

# Obter plano admin
admin_plan = voice_plans.get_admin_plan()
print(f"Plano admin: {admin_plan['name']} - ilimitado")

# Obter plano por ID
plan = voice_plans.get_plan(1)
if plan:
    print(f"Plano ID 1: {plan['name']}")
```

---

## Validações

### Verificar Limite de Vozes

```python
from app.repositories import user_voices

user_id = 1
max_voices = 10
is_unlimited = False

# Verificar se pode criar mais vozes
can_create = user_voices.check_voice_limit(user_id, max_voices, is_unlimited)

if can_create:
    print("✅ Pode criar mais vozes")
else:
    print("❌ Limite atingido")

# Contar vozes atuais
current_count = user_voices.count_user_voices(user_id)
print(f"Vozes atuais: {current_count}/{max_voices}")
```

### Validar Propriedade de Voz

```python
from app.repositories import user_voices

voice_id = "abc123"
user_id = 1

voice = user_voices.get_voice(voice_id)

if voice and voice["user_id"] == user_id:
    print("✅ Usuário é dono da voz")
else:
    print("❌ Usuário não é dono da voz")
```

### Verificar Permissão

```python
from app.auth import get_current_user

def check_audio_permission(request):
    user = get_current_user(request)
    
    if not user:
        return False, "Usuário não autenticado"
    
    if "omnivoice_audio" not in user.get("permissions", []):
        return False, "Sem permissão para gerenciar vozes"
    
    return True, None

# Uso
has_permission, error = check_audio_permission(request)
if not has_permission:
    print(f"❌ {error}")
```

---

## Casos de Uso

### Caso 1: Criar Voz com Validações Completas

```python
from app import omni_voices as voices_mgr
from app.repositories import users as users_repo, user_voices
from app.auth import get_current_user

def create_voice_with_validation(request, name, audio_bytes, filename, reference_text=""):
    """
    Cria uma voz com todas as validações necessárias.
    
    Returns:
        (success: bool, data: dict | error: str)
    """
    # 1. Verificar autenticação
    user = get_current_user(request)
    if not user:
        return False, "Usuário não autenticado"
    
    # 2. Verificar permissão
    if "omnivoice_audio" not in user.get("permissions", []):
        return False, "Sem permissão para gerenciar vozes"
    
    # 3. Validar entrada
    if not name.strip():
        return False, "Nome da voz é obrigatório"
    
    if len(audio_bytes) < 1024:
        return False, "Arquivo de áudio muito curto ou inválido"
    
    # 4. Obter informações do plano
    plan = user.get("voice_plan", {})
    if not plan:
        return False, "Usuário sem plano de vozes atribuído"
    
    max_voices = plan.get("max_voices", 10)
    is_unlimited = plan.get("is_unlimited", False)
    
    # 5. Verificar limite
    current_count = user_voices.count_user_voices(user["id"])
    if not is_unlimited and current_count >= max_voices:
        return False, f"Limite de {max_voices} vozes atingido"
    
    # 6. Criar voz
    try:
        voice = voices_mgr.save_custom(
            user_id=user["id"],
            name=name,
            content=audio_bytes,
            original_filename=filename,
            reference_text=reference_text,
            max_voices=max_voices,
            is_unlimited=is_unlimited,
        )
        return True, voice
    except Exception as e:
        return False, f"Erro ao criar voz: {str(e)}"

# Uso
success, result = create_voice_with_validation(
    request=request,
    name="Minha Voz",
    audio_bytes=audio_content,
    filename="audio.wav",
    reference_text="Texto de referência"
)

if success:
    print(f"✅ Voz criada: {result['name']}")
else:
    print(f"❌ Erro: {result}")
```

### Caso 2: Listar Vozes com Informações do Plano

```python
from app import omni_voices as voices_mgr
from app.repositories import user_voices
from app.auth import get_current_user

def get_voices_with_plan_info(request):
    """
    Lista vozes do usuário junto com informações do plano.
    
    Returns:
        dict com 'voices' e 'plan_info'
    """
    user = get_current_user(request)
    if not user:
        return None
    
    # Listar vozes
    voices = voices_mgr.list_custom(user["id"])
    
    # Obter informações do plano
    plan = user.get("voice_plan", {})
    max_voices = plan.get("max_voices", 10) if plan else 10
    is_unlimited = plan.get("is_unlimited", False) if plan else False
    current_count = len(voices)
    
    return {
        "voices": voices,
        "plan_info": {
            "name": plan.get("name", "Sem plano") if plan else "Sem plano",
            "max_voices": max_voices,
            "is_unlimited": is_unlimited,
            "current_count": current_count,
            "remaining": max_voices - current_count if not is_unlimited else None,
            "can_create_more": is_unlimited or current_count < max_voices,
        }
    }

# Uso
data = get_voices_with_plan_info(request)
if data:
    print(f"Vozes: {data['plan_info']['current_count']}/{data['plan_info']['max_voices']}")
    print(f"Pode criar mais: {data['plan_info']['can_create_more']}")
```

### Caso 3: Atribuir Plano ao Criar Usuário

```python
from app.repositories import users as users_repo, voice_plans

def create_user_with_plan(email, password, is_admin=False):
    """
    Cria usuário e atribui plano automaticamente.
    
    Args:
        email: Email do usuário
        password: Senha do usuário
        is_admin: Se é administrador
    
    Returns:
        user dict
    """
    # 1. Criar usuário
    user = users_repo.create_user(email, password, is_admin)
    
    # 2. Atribuir plano
    if is_admin:
        plan = voice_plans.get_admin_plan()
    else:
        plan = voice_plans.get_basic_plan()
    
    if plan:
        users_repo.update_user_plan(user["id"], plan["id"])
        print(f"✅ Plano '{plan['name']}' atribuído ao usuário {email}")
    else:
        print("⚠️ Nenhum plano disponível")
    
    return user

# Uso
user = create_user_with_plan("user@example.com", "senha123", is_admin=False)
print(f"Usuário criado: {user['email']}")
```

### Caso 4: Migração de Voz entre Usuários (Admin)

```python
from app.repositories import user_voices
from app.database import SessionLocal
from app.models.user_voice import UserVoice

def transfer_voice(voice_id, from_user_id, to_user_id, admin_user_id):
    """
    Transfere uma voz de um usuário para outro (apenas admin).
    
    Args:
        voice_id: ID da voz
        from_user_id: ID do usuário atual
        to_user_id: ID do usuário destino
        admin_user_id: ID do admin fazendo a operação
    
    Returns:
        (success: bool, message: str)
    """
    # Verificar se é admin (simplificado)
    from app.repositories import users as users_repo
    admin = users_repo.get_user_by_id(admin_user_id)
    if not admin or not admin.get("is_admin"):
        return False, "Apenas administradores podem transferir vozes"
    
    # Verificar se voz existe e pertence ao usuário origem
    voice = user_voices.get_voice(voice_id)
    if not voice or voice["user_id"] != from_user_id:
        return False, "Voz não encontrada ou não pertence ao usuário origem"
    
    # Verificar limite do usuário destino
    to_user = users_repo.get_user_by_id(to_user_id)
    plan = to_user.get("voice_plan", {})
    max_voices = plan.get("max_voices", 10) if plan else 10
    is_unlimited = plan.get("is_unlimited", False) if plan else False
    
    if not user_voices.check_voice_limit(to_user_id, max_voices, is_unlimited):
        return False, f"Usuário destino atingiu limite de {max_voices} vozes"
    
    # Transferir
    with SessionLocal() as session:
        db_voice = session.query(UserVoice).filter_by(voice_id=voice_id).first()
        if db_voice:
            db_voice.user_id = to_user_id
            session.commit()
            return True, f"Voz '{voice['name']}' transferida com sucesso"
    
    return False, "Erro ao transferir voz"

# Uso (apenas admin)
success, message = transfer_voice(
    voice_id="abc123",
    from_user_id=1,
    to_user_id=2,
    admin_user_id=1
)
print(message)
```

### Caso 5: Relatório de Uso de Vozes

```python
from app.repositories import user_voices
from app.database import SessionLocal
from sqlalchemy import func
from app.models.user_voice import UserVoice
from app.models.user import User

def get_voices_usage_report():
    """
    Gera relatório de uso de vozes por usuário.
    
    Returns:
        list de dicts com estatísticas
    """
    with SessionLocal() as session:
        results = (
            session.query(
                User.id,
                User.email,
                User.is_admin,
                func.count(UserVoice.id).label("total_voices")
            )
            .outerjoin(UserVoice, (User.id == UserVoice.user_id) & (UserVoice.is_deleted == False))
            .group_by(User.id, User.email, User.is_admin)
            .all()
        )
        
        report = []
        for row in results:
            user = session.query(User).filter_by(id=row.id).first()
            plan = user.voice_plan if user else None
            
            report.append({
                "user_id": row.id,
                "email": row.email,
                "is_admin": bool(row.is_admin),
                "total_voices": row.total_voices,
                "plan_name": plan.name if plan else "Sem plano",
                "max_voices": plan.max_voices if plan else 0,
                "is_unlimited": plan.is_unlimited if plan else False,
                "usage_percent": (row.total_voices / plan.max_voices * 100) if (plan and not plan.is_unlimited and plan.max_voices > 0) else 0,
            })
        
        return report

# Uso
report = get_voices_usage_report()
for item in report:
    print(f"{item['email']}: {item['total_voices']} vozes ({item['usage_percent']:.1f}% do limite)")
```

---

## 🔌 FastAPI Endpoints

### Exemplo Completo de Endpoint

```python
from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse
from app import omni_voices as voices_mgr
from app.auth import get_current_user
from app.repositories import user_voices

router = APIRouter(prefix="/api/voices", tags=["voices"])

@router.post("/create")
async def create_voice_endpoint(
    request: Request,
    name: str = Form(...),
    reference_text: str = Form(""),
    audio: UploadFile = File(...),
):
    """Cria uma nova voz personalizada."""
    # 1. Autenticação
    user = get_current_user(request)
    if not user:
        return JSONResponse({"error": "Não autenticado"}, status_code=401)
    
    # 2. Permissão
    if "omnivoice_audio" not in user.get("permissions", []):
        return JSONResponse({"error": "Sem permissão"}, status_code=403)
    
    # 3. Validação
    if not name.strip():
        return JSONResponse({"error": "Nome é obrigatório"}, status_code=400)
    
    # 4. Ler áudio
    content = await audio.read()
    if len(content) < 1024:
        return JSONResponse({"error": "Áudio inválido"}, status_code=400)
    
    # 5. Obter plano
    plan = user.get("voice_plan", {})
    max_voices = plan.get("max_voices", 10) if plan else 10
    is_unlimited = plan.get("is_unlimited", False) if plan else False
    
    # 6. Criar voz
    try:
        voice = voices_mgr.save_custom(
            user_id=user["id"],
            name=name,
            content=content,
            original_filename=audio.filename,
            reference_text=reference_text,
            max_voices=max_voices,
            is_unlimited=is_unlimited,
        )
        return JSONResponse({"voice": voice}, status_code=201)
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)

@router.get("/list")
async def list_voices_endpoint(request: Request):
    """Lista vozes do usuário."""
    user = get_current_user(request)
    if not user:
        return JSONResponse({"error": "Não autenticado"}, status_code=401)
    
    voices = voices_mgr.list_custom(user["id"])
    
    plan = user.get("voice_plan", {})
    max_voices = plan.get("max_voices", 10) if plan else 10
    is_unlimited = plan.get("is_unlimited", False) if plan else False
    current_count = len(voices)
    
    return JSONResponse({
        "voices": voices,
        "plan": {
            "name": plan.get("name", "Sem plano") if plan else "Sem plano",
            "max_voices": max_voices,
            "is_unlimited": is_unlimited,
            "current_count": current_count,
            "can_create_more": is_unlimited or current_count < max_voices,
        }
    })

@router.delete("/{voice_id}")
async def delete_voice_endpoint(request: Request, voice_id: str):
    """Deleta uma voz."""
    user = get_current_user(request)
    if not user:
        return JSONResponse({"error": "Não autenticado"}, status_code=401)
    
    success = voices_mgr.delete_custom(voice_id, user["id"])
    
    if success:
        return JSONResponse({"ok": True})
    else:
        return JSONResponse({"error": "Voz não encontrada ou sem permissão"}, status_code=404)
```

---

## 📝 Notas Importantes

1. **Sempre verificar autenticação e permissões**
2. **Usar user_id em todas as operações de vozes**
3. **Validar limites antes de criar vozes**
4. **Soft delete ao invés de hard delete**
5. **Logs para auditoria são importantes**

---

## 🔗 Referências

- [SISTEMA_VOZES.md](SISTEMA_VOZES.md) - Documentação completa
- [GUIA_RAPIDO_VOZES.md](GUIA_RAPIDO_VOZES.md) - Guia rápido
- [CHANGELOG_VOZES.md](CHANGELOG_VOZES.md) - Histórico de mudanças
