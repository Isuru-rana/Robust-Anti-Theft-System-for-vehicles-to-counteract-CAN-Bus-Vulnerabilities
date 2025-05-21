/**
 * @file j1939.cpp
 * @author Isuru Rana (https://github.com/Isuru-rana)
 * @brief J1939 Protocol Implementation for ESP32 with MCP2515
 * @version 1.0
 * 
 * This file implements a J1939 protocol controller for CAN bus communications
 * using the MCP2515 CAN controller on ESP32. It handles both single-frame and
 * multi-frame (transport protocol) J1939 messages.
 * 
 * Features:
 * - Complete J1939 transport protocol implementation (TP.BAM)
 * - Multi-session support with up to 6 concurrent sessions
 * - Automatic session management and timeout handling
 * - JSON-formatted message output for received frames
 * - Bus availability management to prevent collisions
 * - Robust error handling and recovery mechanisms
 * 
 * The J1939 protocol is commonly used in heavy-duty vehicles, industrial
 * equipment, and marine applications. This implementation focuses on:
 * 
 * 1. Message reception:
 *    - Decoding single-frame messages (≤8 bytes)
 *    - Handling multi-frame messages through the transport protocol
 *    - Processing Connection Management (TP.CM) and Data Transfer (TP.DT) PDUs
 *    - Assembling fragmented messages into complete data packets
 * 
 * 2. Message transmission:
 *    - Sending single-frame messages (≤8 bytes)
 *    - Breaking large messages into multiple frames using BAM
 *    - Managing bus access and preventing collisions
 *    - Implementing retry mechanisms for reliability
 * 
 * All received messages are output in a consistent JSON format for easy parsing
 * by other applications in the system.
 * 
 * The complete component can be found at:
 * https://github.com/Isuru-rana/J1939-21-MCP2515-ESPIDF-Component
 * 
 */


#include "j1939.h"
#include "mcp2515/mcp2515.h"
#include "mcp2515/can.h"
#include <inttypes.h>

static const char *TAG = "j1939";

namespace J1939 {

Controller::Controller(MCP2515* mcp, uint8_t source_addr)
    : mcp2515(mcp),
      source_address(source_addr),
      bus_busy(false),
      bus_busy_timeout(0) {
    bus_state_mutex = xSemaphoreCreateMutex();
}

Controller::~Controller() {
    if (bus_state_mutex) {
        vSemaphoreDelete(bus_state_mutex);
    }
}

bool Controller::init() {
    return (bus_state_mutex != NULL);
}

bool Controller::is_valid_session(uint8_t session) {
    return (session == SESSION_A || session == SESSION_B || session == SESSION_C ||
            session == SESSION_D || session == SESSION_E || session == SESSION_F);
}

const char* Controller::session_name(uint8_t session) {
    switch (session) {
    case SESSION_A: return "A";
    case SESSION_B: return "B";
    case SESSION_C: return "C";
    case SESSION_D: return "D";
    case SESSION_E: return "E";
    case SESSION_F: return "F";
    default: return "Unknown";
    }
}

const char* Controller::pgn_to_string(uint32_t pgn) {
    switch (pgn) {
    case PGN_REQUEST:
        return "Request";
    case PGN_TP_CM:
        return "TP_CM";
    case PGN_TP_DT:
        return "TP_DT";
    case PGN_ACK:
        return "Acknowledgment";
    case PGN_COMPONENT_ID:
        return "Component Identification";
    case PGN_SOFTWARE_ID:
        return "Software Identification";
    case PGN_PEER_TO_PEER_MESSAGE:
        return "Peer to peer";
    case PGN_GROUP_MESSAGE:
        return "Broadcast";
    case PGN_EXTRA:
        return "extra PGN";
    case PGN_SINGLE_FRAME_TEST:
        return "Single Frame Test PGN";
    default:
        return "Unknown PGN";
    }
}

bool Controller::is_bus_available() {
    bool available = true;

    if (xSemaphoreTake(bus_state_mutex, pdMS_TO_TICKS(100)) == pdTRUE) {
        if (bus_busy) {
            uint32_t current_time = esp_log_timestamp();
            if (current_time > bus_busy_timeout) {
                ESP_LOGW(TAG, "BAM session timed out, releasing bus");
                bus_busy = false;
                active_bam_sessions.clear();
                available = true;
            } else {
                available = false;
            }
        }
        xSemaphoreGive(bus_state_mutex);
    } else {
        available = false;
    }

    return available;
}

bool Controller::is_session_valid(uint8_t session_number, uint8_t src_addr) {
    if (!is_valid_session(session_number)) {
        return false;
    }

    uint16_t session_id = (session_number << 8) | src_addr;
    auto it = multi_frame_messages.find(session_id);

    if (it == multi_frame_messages.end()) {
        return true;
    }

    uint32_t current_time = esp_log_timestamp();
    if (current_time - it->second.last_activity_time > SESSION_TIMEOUT_MS) {
        multi_frame_messages.erase(it);

        if (xSemaphoreTake(bus_state_mutex, pdMS_TO_TICKS(100)) == pdTRUE) {
            if (active_bam_sessions.find(session_id) != active_bam_sessions.end()) {
                active_bam_sessions.erase(session_id);

                if (active_bam_sessions.empty()) {
                    bus_busy = false;
                }
            }
            xSemaphoreGive(bus_state_mutex);
        }
        return true;
    }
    return false;
}

void Controller::cleanup_stale_sessions() {
    uint32_t current_time = esp_log_timestamp();
    std::vector<uint16_t> sessions_to_remove;

    for (const auto &item : multi_frame_messages) {
        if (current_time - item.second.last_activity_time > SESSION_TIMEOUT_MS) {
            uint8_t session = (item.first >> 8) & 0xFF;
            uint8_t src = item.first & 0xFF;
            ESP_LOGW(TAG, "Removing stale session %s (0x%X) from src 0x%02X",
                    session_name(session), session, src);
            sessions_to_remove.push_back(item.first);
        }
    }

    for (uint16_t session_id : sessions_to_remove) {
        multi_frame_messages.erase(session_id);

        if (xSemaphoreTake(bus_state_mutex, pdMS_TO_TICKS(100)) == pdTRUE) {
            if (active_bam_sessions.find(session_id) != active_bam_sessions.end()) {
                active_bam_sessions.erase(session_id);

                if (active_bam_sessions.empty()) {
                    bus_busy = false;
                }
            }
            xSemaphoreGive(bus_state_mutex);
        }
    }
}

void Controller::process_complete_message(const MultiFrameMessage &mfm) {
    printf("{\"pgn\":\"%05" PRIx32 "\",\"sender\":%02X,\"size\":%u,\"data\":\"", 
           mfm.pgn, mfm.source_addr, (unsigned int)mfm.total_size);

    for (size_t i = 0; i < mfm.data.size(); i++) {
        printf("%02X", mfm.data[i]);
    }

    printf("\"}\n");
}

void Controller::parse_tp_cm(const can_frame *frame, uint8_t src_addr) {
    uint8_t control_byte = frame->data[0];
    uint8_t session_number = (control_byte >> 4) & 0x0F;
    const char *session_id_name = session_name(session_number);
    uint16_t session_id = (session_number << 8) | src_addr;

    if (!is_session_valid(session_number, src_addr)) {
        ESP_LOGW(TAG, "Invalid or busy session: %s (0x%X) from src 0x%02X",
                session_id_name, session_number, src_addr);
        return;
    }

    cleanup_stale_sessions();

    if ((control_byte & 0x0F) == 0x00) {
        uint16_t message_size = frame->data[1] | (frame->data[2] << 8);
        uint16_t total_packets = frame->data[3];
        uint32_t pgn = frame->data[5] | (frame->data[6] << 8) | (frame->data[7] << 16);

        uint16_t calculated_packets = (message_size + 6) / 7;

        if (total_packets == 0xFF || total_packets == 0) {
            total_packets = calculated_packets;
        }

        if (message_size == 0 || calculated_packets == 0) {
            ESP_LOGW(TAG, "Invalid BAM parameters: size=%u, packets=%u",
                    message_size, calculated_packets);
            return;
        }

        if (xSemaphoreTake(bus_state_mutex, pdMS_TO_TICKS(100)) == pdTRUE) {
            bus_busy = true;
            bus_busy_timeout = esp_log_timestamp() + (total_packets * 200) + 500;
            active_bam_sessions[session_id] = true;
            xSemaphoreGive(bus_state_mutex);
        }

        MultiFrameMessage &mfm = multi_frame_messages[session_id];
        mfm.data.clear();
        mfm.data.reserve(message_size);
        mfm.total_size = message_size;
        mfm.pgn = pgn;
        mfm.source_addr = src_addr;
        mfm.session_number = session_number;
        mfm.packets_received = 0;
        mfm.total_packets = total_packets;
        mfm.complete = false;
        mfm.last_activity_time = esp_log_timestamp();
    }
    else if ((control_byte & 0x0F) == 0x01) {
        uint16_t message_size = frame->data[1] | (frame->data[2] << 8);
        uint16_t total_packets = frame->data[3];
        uint8_t max_packets = frame->data[4];
        uint32_t pgn = frame->data[5] | (frame->data[6] << 8) | (frame->data[7] << 16);

        uint16_t calculated_packets = (message_size + 6) / 7;

        if (total_packets == 0xFF || total_packets == 0) {
            total_packets = calculated_packets;
        }

        MultiFrameMessage &mfm = multi_frame_messages[session_id];
        mfm.data.clear();
        mfm.data.reserve(message_size);
        mfm.total_size = message_size;
        mfm.pgn = pgn;
        mfm.source_addr = src_addr;
        mfm.session_number = session_number;
        mfm.packets_received = 0;
        mfm.total_packets = total_packets;
        mfm.complete = false;
        mfm.last_activity_time = esp_log_timestamp();
    }
    else if (control_byte == 255) {
        if (multi_frame_messages.find(session_id) != multi_frame_messages.end()) {
            multi_frame_messages.erase(session_id);
        }

        if (xSemaphoreTake(bus_state_mutex, pdMS_TO_TICKS(100)) == pdTRUE) {
            if (active_bam_sessions.find(session_id) != active_bam_sessions.end()) {
                active_bam_sessions.erase(session_id);

                if (active_bam_sessions.empty()) {
                    bus_busy = false;
                }
            }
            xSemaphoreGive(bus_state_mutex);
        }
    }
}

void Controller::parse_tp_dt(const can_frame *frame, uint8_t src_addr) {
    uint8_t first_byte = frame->data[0];
    uint8_t sequence_number = first_byte & 0x0F;
    uint8_t session_number = (first_byte >> 4) & 0x0F;
    uint16_t session_id = (session_number << 8) | src_addr;

    if (sequence_number == 0 || sequence_number > 15) {
        ESP_LOGW(TAG, "Invalid sequence number: %u", sequence_number);
        return;
    }

    auto it = multi_frame_messages.find(session_id);
    if (it == multi_frame_messages.end()) {
        ESP_LOGW(TAG, "Received TP.DT for unknown session: %s (0x%X)",
                session_name(session_number), session_number);
        return;
    }

    MultiFrameMessage &mfm = it->second;
    mfm.last_activity_time = esp_log_timestamp();

    uint8_t expected_seq;
    if (mfm.packets_received % 15 == 0) {
        expected_seq = 1;
    } else {
        expected_seq = (mfm.packets_received % 15) + 1;
    }

    if (sequence_number != expected_seq) {
        ESP_LOGW(TAG, "Out of sequence packet: got %u, expected %u",
                sequence_number, expected_seq);
        multi_frame_messages.erase(it);

        if (xSemaphoreTake(bus_state_mutex, pdMS_TO_TICKS(100)) == pdTRUE) {
            if (active_bam_sessions.find(session_id) != active_bam_sessions.end()) {
                active_bam_sessions.erase(session_id);

                if (active_bam_sessions.empty()) {
                    bus_busy = false;
                }
            }
            xSemaphoreGive(bus_state_mutex);
        }
        return;
    }

    size_t start_pos = mfm.packets_received * 7;
    if (start_pos >= mfm.total_size) {
        ESP_LOGW(TAG, "Data position exceeds message size");
        multi_frame_messages.erase(it);
        return;
    }

    size_t bytes_to_copy = (mfm.total_size - start_pos < 7) ? (mfm.total_size - start_pos) : 7;

    if (mfm.data.size() < start_pos + bytes_to_copy) {
        mfm.data.resize(start_pos + bytes_to_copy);
    }

    memcpy(mfm.data.data() + start_pos, frame->data + 1, bytes_to_copy);
    mfm.packets_received++;

    if (mfm.packets_received >= mfm.total_packets) {
        process_complete_message(mfm);
        multi_frame_messages.erase(it);

        if (xSemaphoreTake(bus_state_mutex, pdMS_TO_TICKS(100)) == pdTRUE) {
            if (active_bam_sessions.find(session_id) != active_bam_sessions.end()) {
                active_bam_sessions.erase(session_id);

                if (active_bam_sessions.empty()) {
                    bus_busy = false;
                }
            }
            xSemaphoreGive(bus_state_mutex);
        }
    }
}

void Controller::decode_j1939_message(const struct can_frame *frame) {
    if (!(frame->can_id & CAN_EFF_FLAG)) {
        return;
    }

    uint32_t id = frame->can_id & CAN_EFF_MASK;
    uint8_t src_addr = id & 0xFF;
    uint8_t pdu_format = (id >> 16) & 0xFF;
    uint8_t pdu_specific = (id >> 8) & 0xFF;
    uint32_t pgn = (id >> 8) & 0x3FFFF;

    bool is_pdu1 = pdu_format < 240;

    if (is_pdu1) {
        pgn &= 0x3FF00;
    }

    pgn |= (uint32_t)pdu_format << 8;

    if (pgn == PGN_TP_CM) {
        parse_tp_cm(frame, src_addr);
    } else if (pgn == PGN_TP_DT) {
        parse_tp_dt(frame, src_addr);
    } else if (pgn == PGN_REQUEST) {
    } else {
        printf("{\"pgn\":\"%05" PRIx32 "\",\"sender\":%02X,\"size\":\"SF\",\"data\":\"", pgn, src_addr);

        for (int i = 0; i < frame->can_dlc; i++) {
            printf("%02X", frame->data[i]);
        }

        printf("\"}\n");
    }
}

bool Controller::send_single_frame_message(uint32_t pgn, uint8_t dst, const uint8_t *data, uint8_t len) {
    if (!is_bus_available()) {
        ESP_LOGW(TAG, "Bus is busy with BAM session, delaying single frame send");
        for (int i = 0; i < 5; i++) {
            vTaskDelay(100 / portTICK_PERIOD_MS);
            if (is_bus_available()) {
                break;
            }

            if (i == 4) {
                ESP_LOGE(TAG, "Bus still busy after retry, aborting single frame send");
                return false;
            }
        }
    }

    if (len > 8) {
        ESP_LOGE(TAG, "Single frame message cannot exceed 8 bytes");
        return false;
    }

    can_frame frame;

    uint8_t pdu_format = (pgn >> 8) & 0xFF;
    uint8_t pdu_specific = pgn & 0xFF;

    frame.can_id = (0x18000000 | ((uint32_t)pdu_format << 16) | ((uint32_t)pdu_specific << 8) | source_address) | CAN_EFF_FLAG;
    frame.can_dlc = len;
    memcpy(frame.data, data, len);

    return (mcp2515->sendMessage(&frame) == MCP2515::ERROR_OK);
}

bool Controller::send_data_packet(uint8_t seq_num, uint8_t dst, const uint8_t *data, uint8_t len, uint8_t session_number) {
    can_frame frame;

    frame.data[0] = seq_num | ((session_number & 0x0F) << 4);

    uint8_t bytes_to_copy = (len > 7) ? 7 : len;
    memcpy(&frame.data[1], data, bytes_to_copy);

    for (int i = bytes_to_copy + 1; i < 8; i++) {
        frame.data[i] = 0xFF;
    }

    frame.can_dlc = 8;
    frame.can_id = (0x18EB0000 | (dst << 8) | source_address) | CAN_EFF_FLAG;

    return (mcp2515->sendMessage(&frame) == MCP2515::ERROR_OK);
}

bool Controller::send_multi_frame_message(uint32_t pgn, const uint8_t *data, uint16_t size) {
    if (!is_bus_available()) {
        ESP_LOGW(TAG, "Bus is busy with another BAM session, delaying multi-frame send");
        for (int i = 0; i < 10; i++) {
            vTaskDelay(200 / portTICK_PERIOD_MS);
            if (is_bus_available()) {
                break;
            }

            if (i == 9) {
                ESP_LOGE(TAG, "Bus still busy after extended retry, aborting multi-frame send");
                return false;
            }
        }
    }

    static const uint8_t working_sessions[] = {2, 3, 6, 7, 10, 11};
    static int session_index = 0;

    uint16_t total_packets = (size + 6) / 7;

    uint8_t this_message_session = working_sessions[session_index];
    session_index = (session_index + 1) % (sizeof(working_sessions) / sizeof(working_sessions[0]));

    can_frame bam_frame;

    bam_frame.data[0] = 0x20 | ((this_message_session & 0x0F) << 4);
    bam_frame.data[1] = size & 0xFF;
    bam_frame.data[2] = (size >> 8) & 0xFF;

    if (total_packets > 255) {
        bam_frame.data[3] = 0xFF;
    } else {
        bam_frame.data[3] = total_packets & 0xFF;
    }

    bam_frame.data[4] = 0xFF;
    bam_frame.data[5] = pgn & 0xFF;
    bam_frame.data[6] = (pgn >> 8) & 0xFF;
    bam_frame.data[7] = (pgn >> 16) & 0xFF;

    bam_frame.can_dlc = 8;
    bam_frame.can_id = (0x18EC0000 | (0xFF << 8) | source_address) | CAN_EFF_FLAG;

    bool bam_sent = false;
    for (int retry = 0; retry < 3 && !bam_sent; retry++) {
        if (mcp2515->sendMessage(&bam_frame) == MCP2515::ERROR_OK) {
            bam_sent = true;
        } else {
            ESP_LOGW(TAG, "Failed to send BAM, retry %d", retry);
            vTaskDelay(10 / portTICK_PERIOD_MS);
        }
    }

    if (!bam_sent) {
        ESP_LOGE(TAG, "Failed to send BAM");
        return false;
    }

    vTaskDelay(10 / portTICK_PERIOD_MS);

    for (uint16_t seq = 1; seq <= total_packets; seq++) {
        uint16_t data_offset = (seq - 1) * 7;

        uint8_t seq_to_send;
        if (seq > 15) {
            seq_to_send = ((seq - 1) % 15) + 1;
        } else {
            seq_to_send = seq;
        }

        if (seq_to_send < 1 || seq_to_send > 15) {
            ESP_LOGW(TAG, "Invalid sequence number %u calculated from seq=%u", seq_to_send, seq);
            seq_to_send = 1;
        }

        uint8_t bytes_to_send = 7;
        if (data_offset + bytes_to_send > size) {
            bytes_to_send = size - data_offset;
        }

        can_frame frame;
        frame.data[0] = seq_to_send | ((this_message_session & 0x0F) << 4);
        memcpy(&frame.data[1], data + data_offset, bytes_to_send);

        for (int i = bytes_to_send + 1; i < 8; i++) {
            frame.data[i] = 0xFF;
        }

        frame.can_dlc = 8;
        frame.can_id = (0x18EB0000 | (0xFF << 8) | source_address) | CAN_EFF_FLAG;

        bool sent = false;
        for (int retry = 0; retry < 3 && !sent; retry++) {
            if (mcp2515->sendMessage(&frame) == MCP2515::ERROR_OK) {
                sent = true;
            } else {
                ESP_LOGW(TAG, "Failed to send packet %d, retry %d", seq, retry);
                vTaskDelay(10 / portTICK_PERIOD_MS);
            }
        }

        if (!sent) {
            ESP_LOGE(TAG, "Failed to send data packet %d after retries", seq);
            return false;
        }

        vTaskDelay(50 / portTICK_PERIOD_MS);
    }
    
    return true;
}

}