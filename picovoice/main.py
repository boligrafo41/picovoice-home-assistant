import paho.mqtt.client as mqtt
import pvporcupine
import pvrhino
import struct
import pyaudio
import os

# Environment variables for MQTT broker and Picovoice Access Key
MQTT_BROKER_ADDRESS = os.getenv('MQTT_BROKER_ADDRESS', '192.168.1.62')
MQTT_BROKER_PORT = int(os.getenv('MQTT_BROKER_PORT', 1883))
PICOVOICE_ACCESS_KEY= os.getenv('PICOVOICE_ACCESS_KEY', '05nuxDRAVjboy6biLTuc/Sy+aHgxCEp00ZM7kDjnibTrXD0QVCbLhw==')

if not PICOVOICE_ACCESS_KEY:
    raise ValueError("PICOVOICE_ACCESS_KEY environment variable is not set.")

print(f"Using Picovoice Access Key: {PICOVOICE_ACCESS_KEY}")


# Configuracón de los ficheros Porcupine y Rhino
PORCUPINE_MODEL_FILE_PATH = "config/Beltran_es_raspberry-pi_v3_0_0.ppn"
RHINO_MODEL_FILE_PATH = "config/Domotica_es_raspberry-pi_v3_0_0.rhn"
PORCUPINE_MODEL_FILE_PATH_ES = "config/porcupine_params_es.pv"
RHINO_MODEL_FILE_PATH_ES = "config/rhino_params_es.pv"

# Inicializar Porcupine para la detecciï¿½n de la palabra clave
porcupine = pvporcupine.create(
    access_key=PICOVOICE_ACCESS_KEY,
    keyword_paths=[PORCUPINE_MODEL_FILE_PATH],
    model_path=PORCUPINE_MODEL_FILE_PATH_ES
)

# Inicializar rhino para Speech-to-Intent
rhino = pvrhino.create(
    access_key=PICOVOICE_ACCESS_KEY,
    context_path=RHINO_MODEL_FILE_PATH,
    model_path=RHINO_MODEL_FILE_PATH_ES
)


# Configurar PyAudio para captura de audio
pa = pyaudio.PyAudio()
audio_stream = pa.open(
    rate=porcupine.sample_rate,
    channels=1,
    format=pyaudio.paInt16,
    input=True,
    frames_per_buffer=porcupine.frame_length,
    input_device_index=2  # Especifica el �ndice del dispositivo de entrada mic usb
)

# Initializacion de cliente MQTT
mqtt_client = mqtt.Client()

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        print("Connected to MQTT Broker!")
    else:
        print(f"Failed to connect, return code {rc}")

def on_disconnect(client, userdata, rc):
    print("Disconnected from MQTT Broker")

mqtt_client.on_connect = on_connect
mqtt_client.on_disconnect = on_disconnect

mqtt_client.connect(MQTT_BROKER_ADDRESS, MQTT_BROKER_PORT, 60)
mqtt_client.loop_start()



def process_intent(intent):
    """
    Procesa la intenciï¿½n y publica el mensaje MQTT correspondiente.
    """
    intent_name = intent.get('intent')
    slots = intent.get('slots', {})

    if intent_name == 'controldeluces':
        accion = slots.get('accion')
        ubicacion = slots.get('ubicacion', 'default_location')
        if accion:
            client.publish(MQTT_TOPIC, f"{accion}_light {ubicacion}")
            print(f"Sent MQTT message to {accion} light in {ubicacion}")
            
    elif intent_name == 'controldetemperatura':
        number = slots.get('pv.TwoDigitInteger')
        if number:
            client.publish(MQTT_TOPIC, f"set_temperature {number}")
            print(f"Sent MQTT message to set temperature to {number} degrees")
            
    elif intent_name == 'controlvoldeaparatos':
        accion_vol = slots.get('acionarvol')
        dispositivo = slots.get('dispositivo', 'default_device')
        if accion_vol:
            client.publish(MQTT_TOPIC, f"{accion_vol}_volume {dispositivo}")
            print(f"Sent MQTT message to {accion_vol} volume of {dispositivo}")
            
    elif intent_name == 'controldealarma':
        alarma = slots.get('alarma')
        if alarma:
            client.publish(MQTT_TOPIC, f"{alarma}_alarm")
            print(f"Sent MQTT message to {alarma} alarm")
            
    elif intent_name == 'controlaparatos':
        accion = slots.get('accion')
        dispositivo = slots.get('dispositivo', 'default_device')
        if accion:
            client.publish(MQTT_TOPIC, f"{accion} {dispositivo}")
            print(f"Sent MQTT message to {accion} {dispositivo}")
    
    # Manejar intenciï¿½n desconocida
    else:
        print(f"Unknown intent: {intent_name}")


def process_audio():
    while True:
        pcm = audio_stream.read(porcupine.frame_length)
        pcm = struct.unpack_from("h" * porcupine.frame_length, pcm)

        # Check for wake word
        keyword_index = porcupine.process(pcm)
        if keyword_index >= 0:
            print("Wake word detected!")
            mqtt_client.publish("home/voice", "Wake word detected")

            # Listen for intent
            print("Listening for intent...")
            rhino.reset()
            while True:
                pcm = audio_stream.read(rhino.frame_length)
                pcm = struct.unpack_from("h" * rhino.frame_length, pcm)
                is_finalized = rhino.process(pcm)
                if is_finalized:
                    intent = rhino.get_inference()
                    if intent.is_understood:
                        process_intent(intent)
                    else:
                        print("Intent not understood")
                    break

if __name__ == "__main__":
    try:
        print("Listening for wake word...")
        process_audio()
    except KeyboardInterrupt:
        print("Terminating...")
    finally:
        audio_stream.close()
        pa.terminate()
        porcupine.delete()
        rhino.delete()
        mqtt_client.loop_stop()
        mqtt_client.disconnect()