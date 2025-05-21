/**
 * @file main.cpp
 * @author Isuru Rana (https://github.com/Isuru-rana)
 * @brief Basic J1939 CAN Bus Node Implementation for ESP32
 * @version 1.0
 * 
 * This application implements a basic J1939 protocol node for CAN bus communications
 * using the MCP2515 CAN controller on ESP32. It provides a simple bridge between
 * serial UART commands and the J1939 protocol over CAN bus.
 * 
 * Features:
 * - Bidirectional communication between UART and J1939 CAN bus
 * - Support for both single-frame and multi-frame message transmission
 * - Interrupt-driven CAN message reception
 * - Message queuing system with timeout handling
 * - JSON output format for received messages
 * 
 * Hardware configuration:
 * - ESP32 connected to MCP2515 CAN controller via SPI
 * - SPI pins: MISO=GPIO19, MOSI=GPIO23, CLK=GPIO18, CS=GPIO5
 * - Interrupt pin: GPIO21
 * 
 * The program processes serial inputs via UART:
 * - Format: [pgn_index,]message
 * - Optional pgn_index (1-3) selects PGN type:
 *   1=PEER_TO_PEER, 2=GROUP_MESSAGE, 3=EXTRA
 * - Messages ≤8 bytes sent as single frame
 * - Messages >8 bytes sent using transport protocol (multi-frame)
 * 
 * All received CAN messages are output in JSON format for easy parsing.
 * 
 * The complete component can be found at:
 * https://github.com/Isuru-rana/J1939-21-MCP2515-ESPIDF-Component
 * 
 */

#include <esp_log.h>
#include <nvs_flash.h>
#include "driver/spi_master.h"
#include "driver/gpio.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/queue.h"
#include <inttypes.h>
#include <string.h>
#include <vector>
#include <map>
#include "driver/uart.h"
#include "esp_vfs_dev.h"
#include "mcp2515/mcp2515.h"
#include "mcp2515/can.h"
#include "j1939.h"

const char *TAG = "j1939_sniffer";
#define SOURCE_ADDR 0x72
#define PIN_NUM_MISO 19
#define PIN_NUM_MOSI 23
#define PIN_NUM_CLK 18
#define PIN_NUM_CS 5
#define PIN_NUM_INT GPIO_NUM_21
#define UART_NUM UART_NUM_0
#define BUF_SIZE 1024

spi_device_handle_t spi_handle;
MCP2515 *mcp2515;
SemaphoreHandle_t spi_mutex = NULL;
static QueueHandle_t gpio_evt_queue = NULL;
J1939::Controller *j1939_controller = NULL;
TaskHandle_t receiver_task_handle = NULL;
TaskHandle_t sender_task_handle = NULL;

void receiver_task(void *pvParameters);
void sender_task(void *pvParameters);

static void IRAM_ATTR gpio_isr_handler(void *arg) {
    uint32_t gpio_num = (uint32_t)arg;
    xQueueSendFromISR(gpio_evt_queue, &gpio_num, NULL);
}

bool init_spi(spi_device_handle_t *spi_handle) {
    spi_bus_config_t buscfg = {};
    buscfg.miso_io_num = PIN_NUM_MISO;
    buscfg.mosi_io_num = PIN_NUM_MOSI;
    buscfg.sclk_io_num = PIN_NUM_CLK;
    buscfg.quadwp_io_num = -1;
    buscfg.quadhd_io_num = -1;
    esp_err_t ret = spi_bus_initialize(VSPI_HOST, &buscfg, 1);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "SPI bus initialization failed: %d", ret);
        return false;
    }
    spi_device_interface_config_t devcfg = {};
    devcfg.clock_speed_hz = 10000000;
    devcfg.mode = 0;
    devcfg.spics_io_num = PIN_NUM_CS;
    devcfg.queue_size = 7;
    ret = spi_bus_add_device(VSPI_HOST, &devcfg, spi_handle);
    if (ret != ESP_OK) {
        ESP_LOGE(TAG, "SPI device add failed: %d", ret);
        return false;
    }
    return true;
}

void init_interrupt_pin() {
    gpio_config_t io_conf = {};
    io_conf.intr_type = GPIO_INTR_NEGEDGE;
    io_conf.pin_bit_mask = (1ULL << PIN_NUM_INT);
    io_conf.mode = GPIO_MODE_INPUT;
    io_conf.pull_up_en = GPIO_PULLUP_ENABLE;
    gpio_config(&io_conf);
    gpio_evt_queue = xQueueCreate(10, sizeof(uint32_t));
    gpio_install_isr_service(0);
    gpio_isr_handler_add(PIN_NUM_INT, gpio_isr_handler, (void *)(uint32_t)PIN_NUM_INT);
    ESP_LOGI(TAG, "GPIO interrupt initialized on pin %d", PIN_NUM_INT);
}

void receiver_task(void *pvParameters) {
    uint32_t gpio_num;
    can_frame frame;
    ESP_LOGI(TAG, "Receiver task started");
    for (;;) {
        if (xQueueReceive(gpio_evt_queue, &gpio_num, pdMS_TO_TICKS(100))) {
            if (xSemaphoreTake(spi_mutex, pdMS_TO_TICKS(100)) == pdTRUE) {
                while (mcp2515->checkReceive()) {
                    if (mcp2515->readMessage(&frame) == MCP2515::ERROR_OK) {
                        j1939_controller->decode_j1939_message(&frame);
                    }
                }
                mcp2515->clearRXInterrupts();
                xSemaphoreGive(spi_mutex);
            }
        } else {
            if (xSemaphoreTake(spi_mutex, pdMS_TO_TICKS(100)) == pdTRUE) {
                if (mcp2515->checkReceive()) {
                    if (mcp2515->readMessage(&frame) == MCP2515::ERROR_OK) {
                        j1939_controller->decode_j1939_message(&frame);
                        mcp2515->clearRXInterrupts();
                    }
                }
                xSemaphoreGive(spi_mutex);
            }
        }
        vTaskDelay(10 / portTICK_PERIOD_MS);
        j1939_controller->cleanup_stale_sessions();
    }
}

void sender_task(void *pvParameters) {
    ESP_LOGI(TAG, "Sender task started");
    uart_config_t uart_config = {
        .baud_rate = 115200,
        .data_bits = UART_DATA_8_BITS,
        .parity = UART_PARITY_DISABLE,
        .stop_bits = UART_STOP_BITS_1,
        .flow_ctrl = UART_HW_FLOWCTRL_DISABLE};
    uart_param_config(UART_NUM, &uart_config);
    uart_driver_install(UART_NUM, BUF_SIZE * 2, 0, 0, NULL, 0);
    
    uint8_t data[BUF_SIZE];
    uint8_t *data_ptr = data;
    size_t data_len = 0;
    
    typedef struct {
        uint32_t pgn;
        uint8_t data[BUF_SIZE];
        size_t len;
        bool is_multi_frame;
        uint32_t timestamp;
    } message_entry_t;
    
    std::vector<message_entry_t> message_queue;
    
    while (1) {
        bool message_sent = false;
        for (auto it = message_queue.begin(); it != message_queue.end();) {
            if (j1939_controller->is_bus_available()) {
                if (xSemaphoreTake(spi_mutex, pdMS_TO_TICKS(100)) == pdTRUE) {
                    bool send_result;
                    if (it->is_multi_frame) {
                        send_result = j1939_controller->send_multi_frame_message(it->pgn, it->data, it->len);
                    } else {
                        send_result = j1939_controller->send_single_frame_message(it->pgn, 0xFF, it->data, it->len);
                    }
                    xSemaphoreGive(spi_mutex);
                    if (send_result) {
                        it = message_queue.erase(it);
                        message_sent = true;
                    } else {
                        uint32_t current_time = esp_log_timestamp();
                        if (current_time - it->timestamp > 5000) {
                            ESP_LOGW(TAG, "Message in queue timed out, removing");
                            it = message_queue.erase(it);
                        } else {
                            ++it;
                        }
                    }
                } else {
                    ++it;
                }
                if (message_sent) {
                    break;
                }
            } else {
                break;
            }
        }
        
        int len = uart_read_bytes(UART_NUM, data_ptr, 1, message_queue.empty() ? portMAX_DELAY : 10);
        if (len > 0) {
            data_ptr++;
            data_len++;
            if (*(data_ptr - 1) == '\n' || *(data_ptr - 1) == '\r' || data_len >= BUF_SIZE - 1) {
                *data_ptr = '\0';
                data_ptr = data;
                if (data_len > 0 && (data[data_len - 1] == '\n' || data[data_len - 1] == '\r')) {
                    data[data_len - 1] = '\0';
                    data_len--;
                }
                
                uint8_t pgn_index = 0;
                uint8_t *message_start = data;
                size_t message_len = data_len;
                uint32_t selected_pgn = J1939::PGN_EXTRA;
                
                if (data_len >= 3 && data[0] >= '1' && data[0] <= '3' && data[1] == ',') {
                    pgn_index = data[0] - '0';
                    message_start = &data[2];
                    message_len = data_len - 2;
                    
                    switch (pgn_index) {
                    case 1:
                        selected_pgn = J1939::PGN_PEER_TO_PEER_MESSAGE;
                        break;
                    case 2:
                        selected_pgn = J1939::PGN_GROUP_MESSAGE;
                        break;
                    case 3:
                        selected_pgn = J1939::PGN_EXTRA;
                        break;
                    default:
                        selected_pgn = J1939::PGN_EXTRA;
                        break;
                    }
                } else {
                    message_start = data;
                    message_len = data_len;
                }
                
                bool sent = false;
                if (j1939_controller->is_bus_available()) {
                    if (xSemaphoreTake(spi_mutex, pdMS_TO_TICKS(100)) == pdTRUE) {
                        if (message_len <= 8) {
                            sent = j1939_controller->send_single_frame_message(selected_pgn, 0xFF, message_start, message_len);
                        } else {
                            sent = j1939_controller->send_multi_frame_message(selected_pgn, message_start, message_len);
                        }
                        xSemaphoreGive(spi_mutex);
                    }
                }
                
                if (!sent) {
                    message_entry_t entry;
                    entry.pgn = selected_pgn;
                    memcpy(entry.data, message_start, message_len);
                    entry.len = message_len;
                    entry.is_multi_frame = (message_len > 8);
                    entry.timestamp = esp_log_timestamp();
                    message_queue.push_back(entry);
                }
                data_len = 0;
                data_ptr = data;
            }
        }
        if (!message_queue.empty() && !message_sent) {
            vTaskDelay(50 / portTICK_PERIOD_MS);
        }
    }
}

extern "C" void app_main(void) {
    esp_err_t ret = nvs_flash_init();
    if (ret == ESP_ERR_NVS_NO_FREE_PAGES || ret == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        ret = nvs_flash_init();
    }
    ESP_ERROR_CHECK(ret);
    
    if (!init_spi(&spi_handle)) {
        ESP_LOGE(TAG, "Failed to initialize SPI");
        return;
    }
    
    mcp2515 = new MCP2515(&spi_handle);
    init_interrupt_pin();
    
    if (mcp2515->reset() != MCP2515::ERROR_OK) {
        ESP_LOGE(TAG, "Failed to reset MCP2515");
        return;
    }
    
    if (mcp2515->setBitrate(CAN_500KBPS, MCP_8MHZ) != MCP2515::ERROR_OK) {
        ESP_LOGE(TAG, "Failed to set MCP2515 bitrate");
        return;
    }
    
    if (mcp2515->setNormalMode() != MCP2515::ERROR_OK) {
        ESP_LOGE(TAG, "Failed to set MCP2515 normal mode");
        return;
    }
    
    mcp2515->setInterruptMask(MCP2515::CANINTF_RX0IF | MCP2515::CANINTF_RX1IF);
    vTaskDelay(100 / portTICK_PERIOD_MS);
    
    spi_mutex = xSemaphoreCreateMutex();
    
    j1939_controller = new J1939::Controller(mcp2515, SOURCE_ADDR);
    if (!j1939_controller->init()) {
        ESP_LOGE(TAG, "Failed to initialize J1939 controller");
        return;
    }
    
    ESP_LOGI(TAG, "MCP2515 and J1939 initialized and ready!");
    
    xTaskCreate(receiver_task, "j1939_receiver", 4096, NULL, 10, &receiver_task_handle);
    xTaskCreate(sender_task, "j1939_sender", 4096, NULL, 5, &sender_task_handle);
}