/**
 * @file main.cpp
 * @author Isuru Rana (https://github.com/Isuru-rana)
 * @brief J1939 CAN Bus Ignition Monitor Module (IMM) for ESP32
 * @version 1.0
 * 
 * This application implements an Immobilizer Module (IMM) for J1939 protocol
 * communication over CAN bus using the MCP2515 controller on ESP32.
 * 
 * Features:
 * - Bidirectional communication between UART and J1939 CAN bus
 * - Support for both JSON-formatted commands and direct CAN message transmission
 * - Built-in LED control for ignition status indication
 * - Message queuing system with timeout handling
 * - Interrupt-driven CAN message reception
 * - Multi-frame message support for large data packets
 * 
 * Hardware configuration:
 * - ESP32 connected to MCP2515 CAN controller via SPI
 * MCP2515:
 * - SPI pins: MISO=GPIO19, MOSI=GPIO23, CLK=GPIO18, CS=GPIO5
 * - Interrupt pin: GPIO21
 * - Status LED: GPIO2 (built-in LED for ignition simulate)
 * 
 * The program processes two types of inputs via UART:
 * 1. JSON messages: Format {"c":"command","d":"data"} for LED control
 *    - Command "np" with data "Ignition ON" turns LED on
 *    - Command "np" with data "Ignition OFF" turns LED off
 *    - Other commands/data trigger temporary LED activation (2000ms)
 * 
 * 2. CAN messages: Format [pgn_index,]message
 *    - Optional pgn_index (1-3) selects PGN type:
 *      1=PEER_TO_PEER, 2=GROUP_MESSAGE, 3=EXTRA
 *    - Messages ≤8 bytes sent as single frame
 *    - Messages >8 bytes sent using transport protocol (multi-frame)
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
#include "cJSON.h"

const char *TAG = "IMM";
#define SOURCE_ADDR 0x32
#define PIN_NUM_MISO 19
#define PIN_NUM_MOSI 23
#define PIN_NUM_CLK 18
#define PIN_NUM_CS 5
#define PIN_NUM_INT GPIO_NUM_21
#define UART_NUM UART_NUM_0
#define BUF_SIZE 1024

#define BUILTIN_LED GPIO_NUM_2

spi_device_handle_t spi_handle;
MCP2515 *mcp2515;
SemaphoreHandle_t spi_mutex = NULL;
static QueueHandle_t gpio_evt_queue = NULL;
J1939::Controller *j1939_controller = NULL;
TaskHandle_t receiver_task_handle = NULL;
TaskHandle_t sender_task_handle = NULL;
TaskHandle_t led_task_handle = NULL;

void receiver_task(void *pvParameters);
void sender_task(void *pvParameters);
void led_control_task(void *pvParameters);

QueueHandle_t led_control_queue = NULL;

typedef struct {
    bool turn_on;
    uint32_t duration_ms;
} led_control_t;

static void IRAM_ATTR gpio_isr_handler(void *arg) {
    uint32_t gpio_num = (uint32_t)arg;
    xQueueSendFromISR(gpio_evt_queue, &gpio_num, NULL);
}

bool process_json_message(const uint8_t *data, size_t len) {
    if (len < 2 || data[0] != '{' || data[len-1] != '}') {
        return false;
    }
    
    char *json_str = (char*)malloc(len + 1);
    if (!json_str) {
        // ESP_LOGE(TAG, "Memory allocation failed");
        return false;
    }
    
    memcpy(json_str, data, len);
    json_str[len] = '\0';
    
    cJSON *root = cJSON_Parse(json_str);
    free(json_str);
    
    if (!root) {
        return false;
    }
    
    cJSON *c_lower = cJSON_GetObjectItem(root, "c");
    cJSON *c_upper = cJSON_GetObjectItem(root, "C");
    cJSON *d_lower = cJSON_GetObjectItem(root, "d");
    cJSON *d_upper = cJSON_GetObjectItem(root, "D");
    
    cJSON *c = c_lower ? c_lower : c_upper;
    cJSON *d = d_lower ? d_lower : d_upper;
    
    bool is_valid = (c && d && 
                    cJSON_IsString(c) && 
                    cJSON_IsString(d));
    
    if (is_valid) {
        // ESP_LOGI(TAG, "Valid JSON message detected with fields c/C and d/D");
        
        const char* cmd = cJSON_GetStringValue(c);
        const char* data_val = cJSON_GetStringValue(d);
        
        if (strcmp(cmd, "np") == 0) {
            // ESP_LOGI(TAG, "Command 'np' detected with data: %s", data_val);
            
            led_control_t led_msg;
            
            if (strcmp(data_val, "Ignition ON") == 0) {
                // ESP_LOGI(TAG, "Turning LED permanently ON");
                led_msg.turn_on = true;
                led_msg.duration_ms = 0;
                xQueueSend(led_control_queue, &led_msg, portMAX_DELAY);
            } 
            else if (strcmp(data_val, "Ignition OFF") == 0) {
                // ESP_LOGI(TAG, "Turning LED permanently OFF");
                led_msg.turn_on = false;
                led_msg.duration_ms = 0;
                xQueueSend(led_control_queue, &led_msg, portMAX_DELAY);
            }
            else {
                // ESP_LOGI(TAG, "Other 'np' command, blinking LED");
                led_msg.turn_on = true;
                led_msg.duration_ms = 2000;
                xQueueSend(led_control_queue, &led_msg, portMAX_DELAY);
            }
        }
        else {
            // ESP_LOGI(TAG, "Command '%s' detected, blinking LED", cmd);
            led_control_t led_msg;
            led_msg.turn_on = true;
            led_msg.duration_ms = 2000;
            xQueueSend(led_control_queue, &led_msg, portMAX_DELAY);
        }
    }
    
    cJSON_Delete(root);
    return is_valid;
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
        // ESP_LOGE(TAG, "SPI bus initialization failed: %d", ret);
        return false;
    }
    spi_device_interface_config_t devcfg = {};
    devcfg.clock_speed_hz = 10000000;
    devcfg.mode = 0;
    devcfg.spics_io_num = PIN_NUM_CS;
    devcfg.queue_size = 7;
    ret = spi_bus_add_device(VSPI_HOST, &devcfg, spi_handle);
    if (ret != ESP_OK) {
        // ESP_LOGE(TAG, "SPI device add failed: %d", ret);
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
    // ESP_LOGI(TAG, "GPIO interrupt initialized on pin %d", PIN_NUM_INT);
}

void init_led() {
    gpio_config_t io_conf = {};
    io_conf.intr_type = GPIO_INTR_DISABLE;
    io_conf.mode = GPIO_MODE_OUTPUT;
    io_conf.pin_bit_mask = (1ULL << BUILTIN_LED);
    io_conf.pull_down_en = GPIO_PULLDOWN_DISABLE;
    io_conf.pull_up_en = GPIO_PULLUP_DISABLE;
    gpio_config(&io_conf);
    
    gpio_set_level(BUILTIN_LED, 0);
    // ESP_LOGI(TAG, "Built-in LED initialized on pin %d", BUILTIN_LED);
}

void led_control_task(void *pvParameters) {
    led_control_t control_msg;
    
    for (;;) {
        if (xQueueReceive(led_control_queue, &control_msg, portMAX_DELAY)) {
            if (control_msg.turn_on) {
                if (control_msg.duration_ms > 0) {
                    // ESP_LOGI(TAG, "Turning on LED for %" PRIu32 " ms", control_msg.duration_ms);
                    gpio_set_level(BUILTIN_LED, 1);
                    vTaskDelay(control_msg.duration_ms / portTICK_PERIOD_MS);
                    gpio_set_level(BUILTIN_LED, 0);
                    // ESP_LOGI(TAG, "LED turned off");
                } else {
                    // ESP_LOGI(TAG, "Turning on LED permanently");
                    gpio_set_level(BUILTIN_LED, 1);
                }
            } else {
                // ESP_LOGI(TAG, "Turning off LED");
                gpio_set_level(BUILTIN_LED, 0);
            }
        }
    }
}

void receiver_task(void *pvParameters) {
    uint32_t gpio_num;
    can_frame frame;
    // ESP_LOGI(TAG, "Receiver task started");
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
    // ESP_LOGI(TAG, "Sender task started");
    uart_config_t uart_config = {
        .baud_rate = 115200,
        .data_bits = UART_DATA_8_BITS,
        .parity = UART_PARITY_DISABLE,
        .stop_bits = UART_STOP_BITS_1,
        .flow_ctrl = UART_HW_FLOWCTRL_DISABLE,
        .rx_flow_ctrl_thresh = 0,
        .source_clk = UART_SCLK_APB,
        .flags = 0
    };
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
                            // ESP_LOGW(TAG, "Message in queue timed out, removing");
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
                
                if (process_json_message(data, data_len)) {
                    // ESP_LOGI(TAG, "JSON message not sent to CAN bus");
                } else {
                    // ESP_LOGI(TAG, "Non-JSON message, sending to CAN bus");
                    
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
        // ESP_LOGE(TAG, "Failed to initialize SPI");
        return;
    }
    
    mcp2515 = new MCP2515(&spi_handle);
    init_interrupt_pin();
    init_led();
    
    if (mcp2515->reset() != MCP2515::ERROR_OK) {
        // ESP_LOGE(TAG, "Failed to reset MCP2515");
        return;
    }
    
    if (mcp2515->setBitrate(CAN_500KBPS, MCP_8MHZ) != MCP2515::ERROR_OK) {
        // ESP_LOGE(TAG, "Failed to set MCP2515 bitrate");
        return;
    }
    
    if (mcp2515->setNormalMode() != MCP2515::ERROR_OK) {
        // ESP_LOGE(TAG, "Failed to set MCP2515 normal mode");
        return;
    }
    
    mcp2515->setInterruptMask(MCP2515::CANINTF_RX0IF | MCP2515::CANINTF_RX1IF);
    vTaskDelay(100 / portTICK_PERIOD_MS);
    
    spi_mutex = xSemaphoreCreateMutex();
    
    led_control_queue = xQueueCreate(5, sizeof(led_control_t));
    
    j1939_controller = new J1939::Controller(mcp2515, SOURCE_ADDR);
    if (!j1939_controller->init()) {
        // ESP_LOGE(TAG, "Failed to initialize J1939 controller");
        return;
    }
    
    // ESP_LOGI(TAG, "MCP2515 and J1939 initialized and ready!");
    
    xTaskCreate(led_control_task, "led_control", 2048, NULL, 5, &led_task_handle);
    
    xTaskCreate(receiver_task, "j1939_receiver", 4096, NULL, 10, &receiver_task_handle);
    xTaskCreate(sender_task, "j1939_sender", 4096, NULL, 5, &sender_task_handle);
}