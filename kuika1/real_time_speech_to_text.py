import speech_recognition as sr

def speech_to_text():
    # Create a recognizer object
    recognizer = sr.Recognizer()

    # Use the default microphone as the audio source
    with sr.Microphone() as source:
        print("Dinliyorum... Konuşmaya başlayın. Durdurmak için Ctrl+C tuşlarına basın.")

        # Adjust for ambient noise
        recognizer.adjust_for_ambient_noise(source)

        try:
            while True:
                print("Dinleniyor...")
                audio = recognizer.listen(source)

                try:
                    # Use Google Speech Recognition to convert audio to text, specifying Turkish
                    text = recognizer.recognize_google(audio, language="tr-TR")
                    print("Söylediğiniz:", text)
                except sr.UnknownValueError:
                    print("Üzgünüm, söylediğinizi anlayamadım.")
                except sr.RequestError as e:
                    print("Konuşma tanıma servisinden sonuç istenemedi; {0}".format(e))

        except KeyboardInterrupt:
            print("\nProgram durduruldu.")

if __name__ == "__main__":
    speech_to_text()