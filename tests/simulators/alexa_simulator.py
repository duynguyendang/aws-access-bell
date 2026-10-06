import asyncio
import platform
import shutil
from dataclasses import dataclass


@dataclass
class AlexaUtterance:
    event_id: str
    text: str
    language: str
    spoken: bool = False


class AlexaSimulator:
    def __init__(self, use_tts: bool = True):
        self.use_tts = use_tts
        self.utterances: list[AlexaUtterance] = []
        self._tts_available = self._check_tts()

    def _check_tts(self) -> bool:
        if not self.use_tts:
            return False
        system = platform.system()
        if system == "Darwin":
            return shutil.which("say") is not None
        if system == "Linux":
            return shutil.which("espeak-ng") is not None or shutil.which("espeak") is not None
        return False

    async def announce(self, event_id: str, text: str, language: str = "en") -> AlexaUtterance:
        utterance = AlexaUtterance(
            event_id=str(event_id),
            text=text,
            language=language,
        )

        print(f"\nALEXA VOICE [{language.upper()}]: \"{text}\"")

        if self._tts_available:
            try:
                await self._speak(text, language)
                utterance.spoken = True
            except Exception as exc:
                print(f"TTS error: {exc}")

        self.utterances.append(utterance)
        return utterance

    async def _speak(self, text: str, language: str):
        system = platform.system()
        if system == "Darwin":
            voice = "Samantha" if language == "en" else "Linh"
            cmd = ["say", "-v", voice, text]
        elif system == "Linux":
            espeak = shutil.which("espeak-ng") or shutil.which("espeak")
            lang_flag = "en" if language == "en" else "vi"
            cmd = [espeak, "-v", lang_flag, text]
        else:
            return

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.wait()

    def get_announcements_for_event(self, event_id: str) -> list[AlexaUtterance]:
        return [u for u in self.utterances if str(u.event_id) == str(event_id)]


async def demo():
    sim = AlexaSimulator(use_tts=True)
    await sim.announce("evt_001", "A delivery person is at the front door with a package.", "en")


if __name__ == "__main__":
    asyncio.run(demo())
