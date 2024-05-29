#include <mic.h>
#include <hal/nrf_pdm.h>

/*
This example collects data from both a over-the-air microphone (OTA) and a bone conduction microphone (BCM)
They are configured as: OTA - select pin connects to VCC (left channel), BCM - select pin connects to GND (right channel)
OTA used is https://www.adafruit.com/product/4346, by default select connects to VCC (see https://learn.adafruit.com/assets/80176)
BCM used is V2S200D (https://www.knowles.com/docs/default-source/default-document-library/kno_v2s200d-datasheet.pdf)
We used the V2S200D on flex PCB (https://www.digikey.com/en/products/detail/knowles/KAS-700-0177/18670178)
                     + flex adapter (https://www.knowles.com/docs/default-source/default-document-library/kca2733-mic-on-flex-adapter-product-brief.pdf)
  Flex adapter connection: 
      P(PWR) - nRF 3.3V
      O(OUT) - nRF DIN
      G(GND) - nRF GND
      K(CLK) - nRF CLK
      S(select) - GND, this is for configuring the PDM to right channel
*/

// PDM to nRF Connection
// DIN - 0 (Xiao), P0.02 (nRF52840)
// CLK - 1 (Xiao), P0.03 (nRF52840)
// PWR - 3V3

// Settings
#define DEBUG 1                 // Enable pin pulse during ISR  
#define SAMPLES 1600

// Frame
const uint8_t startFrame[] = {0x00, 0x11, 0x22, 0x33, (SAMPLES >> 8) & 0xFF, SAMPLES & 0xFF};

mic_config_t mic_config{
  .channel_cnt = 2,
  .sampling_rate = 16000,
  .buf_size = 1600,
  .debug_pin = LED_BUILTIN                // Toggles each DAC ISR (if DEBUG is set to 1)
};

NRF52840_ADC_Class Mic(&mic_config);

int16_t recording_buf[SAMPLES];
volatile static bool record_ready = false;

void setup() {
  Serial.begin(115200);
  while (!Serial) {
    delay(10);
  }

  Mic.set_callback(audio_rec_callback);

  if (!Mic.begin()) {
    Serial.println("Mic initialization failed");
    while (1);
  }
  // Mic.setGain(1);
  // Left Mic, Right BCM, BCM Larger number is lower gain Mic lower number is lower
  // BCM gain seems to cap at 127
  nrf_pdm_gain_set(50, 100);

  Serial.println("Mic initialization done.");
}

unsigned long lastBuf = millis();
void loop() {
  if (record_ready) {
    //  Serial.println("Finished sampling");

//    for (int i = 0; i < SAMPLES; i++) {
//      int16_t sample = recording_buf[i];
//      Serial.print(sample);
//      Serial.print(",");
//    }
//    Serial.println();

        Serial.write((uint8_t *) &startFrame, 6);
        Serial.write((uint8_t *) &recording_buf, SAMPLES * sizeof(int16_t));

    
    //    Serial.println();
    //    Serial.println(millis() - lastBuf);
    //    lastBuf = millis();

    record_ready = false;
  }
}

static void audio_rec_callback(uint16_t *buf, uint32_t buf_len) {
  static uint32_t idx = 0;
  // Copy samples from DMA buffer to inference buffer
  for (uint32_t i = 0; i < buf_len; i++) {
    recording_buf[idx++] = buf[i];
    if (idx >= SAMPLES) {
      idx = 0;
      record_ready = true;
      break;
    }
  }
}
