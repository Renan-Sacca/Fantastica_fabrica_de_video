#!/usr/bin/env python3
"""
Script de migração de vozes do formato JSON antigo para o novo sistema de banco de dados.

Este script:
1. Lê o arquivo _custom_voices.json antigo
2. Cria entradas na tabela user_voices para cada voz
3. Mantém os arquivos de áudio no mesmo local
4. Faz backup do arquivo JSON antigo

Uso:
    python migrate_voices.py --user-id 1
    python migrate_voices.py --user-id 1 --json-path /caminho/para/_custom_voices.json
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

# Adiciona o diretório web ao path para importar módulos
sys.path.insert(0, str(Path(__file__).parent / "web"))

from app.database import SessionLocal
from app.models.user_voice import UserVoice


def migrate_voices(json_path: Path, user_id: int, dry_run: bool = False):
    """
    Migra vozes do arquivo JSON para o banco de dados.
    
    Args:
        json_path: Caminho para o arquivo _custom_voices.json
        user_id: ID do usuário que será dono das vozes migradas
        dry_run: Se True, apenas mostra o que seria feito sem salvar
    """
    if not json_path.exists():
        print(f"❌ Arquivo não encontrado: {json_path}")
        return
    
    try:
        voices_data = json.loads(json_path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"❌ Erro ao ler arquivo JSON: {e}")
        return
    
    if not voices_data:
        print("⚠️  Arquivo JSON está vazio, nada para migrar.")
        return
    
    print(f"📋 Encontradas {len(voices_data)} vozes para migrar")
    print(f"👤 Usuário destino: {user_id}")
    print(f"🔧 Modo: {'DRY RUN (simulação)' if dry_run else 'MIGRAÇÃO REAL'}")
    print()
    
    migrated = 0
    skipped = 0
    
    with SessionLocal() as session:
        for voice_id, info in voices_data.items():
            voice_name = info.get("name", "Sem nome")
            filename = info.get("filename", "")
            reference_text = info.get("reference_text", "")
            
            # Verifica se já existe
            existing = session.query(UserVoice).filter_by(voice_id=voice_id).first()
            if existing:
                print(f"⏭️  Pulando: {voice_name} (ID: {voice_id}) - já existe no banco")
                skipped += 1
                continue
            
            if dry_run:
                print(f"✓ Seria migrada: {voice_name} (ID: {voice_id}, arquivo: {filename})")
                migrated += 1
            else:
                try:
                    voice = UserVoice(
                        voice_id=voice_id,
                        user_id=user_id,
                        name=voice_name,
                        filename=filename,
                        reference_text=reference_text,
                        is_deleted=False,
                    )
                    session.add(voice)
                    session.commit()
                    print(f"✅ Migrada: {voice_name} (ID: {voice_id})")
                    migrated += 1
                except Exception as e:
                    print(f"❌ Erro ao migrar {voice_name}: {e}")
                    session.rollback()
    
    print()
    print("=" * 60)
    print(f"✅ Migradas: {migrated}")
    print(f"⏭️  Puladas: {skipped}")
    print("=" * 60)
    
    if not dry_run and migrated > 0:
        # Faz backup do arquivo JSON
        backup_path = json_path.with_suffix(f".backup-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json")
        json_path.rename(backup_path)
        print(f"💾 Backup criado: {backup_path}")
        print()
        print("⚠️  IMPORTANTE: As vozes foram migradas para o banco de dados.")
        print("   Os arquivos de áudio continuam no mesmo local.")
        print("   O arquivo JSON original foi renomeado como backup.")


def main():
    parser = argparse.ArgumentParser(
        description="Migra vozes do formato JSON antigo para o banco de dados"
    )
    parser.add_argument(
        "--user-id",
        type=int,
        required=True,
        help="ID do usuário que será dono das vozes migradas",
    )
    parser.add_argument(
        "--json-path",
        type=Path,
        default=Path(__file__).parent / "tts3" / "data" / "voices" / "_custom_voices.json",
        help="Caminho para o arquivo _custom_voices.json (padrão: tts3/data/voices/_custom_voices.json)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Apenas simula a migração sem salvar no banco",
    )
    
    args = parser.parse_args()
    
    print("🔄 Iniciando migração de vozes")
    print("=" * 60)
    migrate_voices(args.json_path, args.user_id, args.dry_run)


if __name__ == "__main__":
    main()
