#!/usr/bin/env python3
"""
Script para inicializar os planos de vozes padrão.

Este script cria os planos básico e admin caso ainda não existam no banco de dados.

Uso:
    python init_voice_plans.py
"""
import sys
from pathlib import Path

# Adiciona o diretório web ao path para importar módulos
sys.path.insert(0, str(Path(__file__).parent / "web"))

from app.database import SessionLocal
from app.models.voice_plan import VoicePlan


def init_plans():
    """Cria os planos padrão se não existirem."""
    
    plans_to_create = [
        {
            "name": "Plano Básico",
            "description": "Plano inicial com até 10 vozes personalizadas",
            "max_voices": 10,
            "is_unlimited": False,
            "is_active": True,
        },
        {
            "name": "Plano Admin",
            "description": "Plano administrativo com vozes ilimitadas",
            "max_voices": 0,
            "is_unlimited": True,
            "is_active": True,
        },
    ]
    
    with SessionLocal() as session:
        for plan_data in plans_to_create:
            # Verifica se já existe
            existing = session.query(VoicePlan).filter_by(name=plan_data["name"]).first()
            
            if existing:
                print(f"⏭️  Plano '{plan_data['name']}' já existe (ID: {existing.id})")
                continue
            
            # Cria novo plano
            plan = VoicePlan(**plan_data)
            session.add(plan)
            session.commit()
            session.refresh(plan)
            print(f"✅ Plano '{plan.name}' criado (ID: {plan.id})")
    
    print()
    print("=" * 60)
    print("✅ Inicialização concluída!")
    print("=" * 60)
    print()
    print("📋 Próximos passos:")
    print("  1. Atribuir planos aos usuários existentes (se necessário):")
    print("     UPDATE users SET voice_plan_id = 1 WHERE is_admin = 0;")
    print("     UPDATE users SET voice_plan_id = 2 WHERE is_admin = 1;")
    print()
    print("  2. Migrar vozes antigas (se existirem):")
    print("     python migrate_voices.py --user-id 1")


if __name__ == "__main__":
    print("🔄 Inicializando planos de vozes padrão")
    print("=" * 60)
    init_plans()
