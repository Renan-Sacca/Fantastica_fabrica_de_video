import pymysql

connection = pymysql.connect(
    host='72.60.140.18',
    port=3306,
    user='user_pessoal',
    password='Re+991352443',
    database='fabrica_video_db',
    charset='utf8mb4'
)

cursor = connection.cursor()
cursor.execute("""
    ALTER TABLE audio_presets 
    MODIFY COLUMN language_id VARCHAR(10) NULL 
    COMMENT 'Código ISO do idioma (ex: pt-BR, en-US)'
""")
connection.commit()
cursor.close()
connection.close()

print('✅ Campo language_id atualizado com comentário!')
