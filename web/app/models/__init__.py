"""Models do banco de dados, separados por domínio."""
from .job import Job
from .whatsapp import WhatsAppJob
from .whatsapp_extract import WhatsAppExtractJob
from .video_bg import VideoBgJob
from .video_compositor import VideoCompositorJob
from .text_correction import TextCorrectionJob
from .audio_job import AudioJob
from .user import User
from .permission import Permission
from .voice_plan import VoicePlan
from .user_voice import UserVoice
from .audio_preset import AudioPreset
from .compositor_template import CompositorTemplate

__all__ = [
    "Job",
    "WhatsAppJob",
    "WhatsAppExtractJob",
    "VideoBgJob",
    "VideoCompositorJob",
    "TextCorrectionJob",
    "AudioJob",
    "User",
    "Permission",
    "VoicePlan",
    "UserVoice",
    "AudioPreset",
    "CompositorTemplate",
]
