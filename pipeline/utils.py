import numpy as np


def print_audio_info(audio: np.ndarray, sample_rate: int):

    duration = len(audio) / sample_rate

    print("=" * 50)
    print("Audio Information")
    print("=" * 50)

    print(f"Sample Rate : {sample_rate} Hz")
    print(f"Samples     : {len(audio)}")
    print(f"Duration    : {duration:.2f} s")

    print("=" * 50)
