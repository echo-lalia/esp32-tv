#ifdef TDISPLAY        // TODO: We need that because the current "touch-down" variant don't compile with these definitions
#include <Arduino.h>
#include <driver/rtc_io.h>
#include <esp_bt.h>
#include <esp_bt_main.h>
#endif

void powerDeepSeep() {
#ifdef TDISPLAY
  digitalWrite(ADC_EN, LOW);
  delay(10);
  rtc_gpio_init(GPIO_NUM_14);
  rtc_gpio_set_direction(GPIO_NUM_14, RTC_GPIO_MODE_OUTPUT_ONLY);
  rtc_gpio_set_level(GPIO_NUM_14, 1);
  esp_bluedroid_disable();
  esp_bt_controller_disable();
  esp_deep_sleep_disable_rom_logging();
  // esp_sleep_pd_config(ESP_PD_DOMAIN_RTC_SLOW_MEM, ESP_PD_OPTION_OFF);
  // esp_sleep_pd_config(ESP_PD_DOMAIN_RTC_FAST_MEM, ESP_PD_OPTION_OFF);
  // esp_sleep_pd_config(ESP_PD_DOMAIN_RTC_PERIPH, ESP_PD_OPTION_OFF);
  delay(500);
  esp_deep_sleep_start();
#endif
}

void powerInit() {
#ifdef TDISPLAY
  pinMode(HW_EN, OUTPUT);
  digitalWrite(HW_EN, HIGH);  // step-up on
#endif
}
