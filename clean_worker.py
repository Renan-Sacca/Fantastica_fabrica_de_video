import re
with open('worker/main.py', 'r', encoding='utf-8') as f:
    content = f.read()

new_process_msg = '''    async def _process_message(self, body: str):
        job_id = None
        try:
            payload = json.loads(body)
            job_id = payload.get('job_id')
            video_type = payload.get('video_type', 'whatsapp')
            self.drive = DriveClient(TOKEN_FILE)
            if not job_id:
                logger.error("Payload inválido: sem job_id")
                return

            if video_type == "whatsapp":
                from renderers.whatsapp.processor import WhatsAppProcessor
                processor = WhatsAppProcessor(job_id, self.drive, self._publish_progress)
                await processor.process()
            else:
                logger.error(f"Video type '{video_type}' não suportado ou sem processador específico.")

        except Exception as e:
            logger.exception(f"[{job_id}] Falha ao delegar processamento do job:")
            if job_id:
                await self._publish_progress(job_id, "error", 0, f"Erro: {e}")

if __name__ == "__main__":'''

content = re.sub(r"    async def _process_message\(self, body: str\):.*?if __name__ == \"__main__\":", new_process_msg, content, flags=re.DOTALL)

with open('worker/main.py', 'w', encoding='utf-8') as f:
    f.write(content)
print("worker/main.py rewritten!")
