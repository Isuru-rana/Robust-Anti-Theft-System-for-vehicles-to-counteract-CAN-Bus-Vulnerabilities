#pragma once

#include <stdint.h>
#include <vector>
#include <map>
#include <string.h>
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "esp_log.h"
#include "driver/spi_master.h"

// Forward declarations for MCP2515 classes
class MCP2515;
struct can_frame;

namespace J1939 {
    // PGN definitions
    constexpr uint32_t PGN_SINGLE_FRAME_TEST = 0xEF02;
    constexpr uint32_t PGN_PEER_TO_PEER_MESSAGE = 0xEF00;
    constexpr uint32_t PGN_GROUP_MESSAGE = 0xEF10;
    constexpr uint32_t PGN_EXTRA = 0xEF20;
    constexpr uint32_t PGN_SOFTWARE_ID = 0xFEDA;
    constexpr uint32_t PGN_COMPONENT_ID = 0xFEEB;
    constexpr uint32_t PGN_TP_CM = 0xEC00;
    constexpr uint32_t PGN_TP_DT = 0xEB00;
    constexpr uint32_t PGN_REQUEST = 0xEA00;
    constexpr uint32_t PGN_ACK = 0xE800;

    // Session values
    constexpr uint8_t SESSION_A = 2;
    constexpr uint8_t SESSION_B = 3;
    constexpr uint8_t SESSION_C = 6;
    constexpr uint8_t SESSION_D = 7;
    constexpr uint8_t SESSION_E = 10;
    constexpr uint8_t SESSION_F = 11;
    
    // Default configuration
    constexpr uint32_t BUS_BUSY_TIMEOUT_MS = 2000;
    constexpr uint32_t SESSION_TIMEOUT_MS = 1000;
    constexpr uint8_t DEFAULT_SOURCE_ADDRESS = 0x32;

    // Structure to hold multi-frame message data
    struct MultiFrameMessage {
        std::vector<uint8_t> data;
        size_t total_size;
        uint32_t pgn;
        uint8_t source_addr;
        uint8_t session_number;
        uint16_t packets_received;
        uint16_t total_packets;
        bool complete;
        uint32_t last_activity_time;
    };

    // J1939 Protocol Controller Class
    class Controller {
    public:
        // Constructor & Destructor
        Controller(MCP2515* mcp, uint8_t source_addr = DEFAULT_SOURCE_ADDRESS);
        ~Controller();
        
        // Initialization
        bool init();
        
        // Message handling
        void decode_j1939_message(const can_frame* frame);
        
        // Transport Protocol handlers
        void parse_tp_cm(const can_frame* frame, uint8_t src_addr);
        void parse_tp_dt(const can_frame* frame, uint8_t src_addr);
        
        // Send methods
        bool send_single_frame_message(uint32_t pgn, uint8_t dst, const uint8_t* data, uint8_t len);
        bool send_multi_frame_message(uint32_t pgn, const uint8_t* data, uint16_t size);
        bool send_data_packet(uint8_t seq_num, uint8_t dst, const uint8_t* data, uint8_t len, uint8_t session_number);
        
        // Session management
        bool is_bus_available();
        bool is_session_valid(uint8_t session_number, uint8_t src_addr);
        bool is_valid_session(uint8_t session);
        void cleanup_stale_sessions();
        void process_complete_message(const MultiFrameMessage& mfm);
        const char* session_name(uint8_t session);
        
        // Utility
        static const char* pgn_to_string(uint32_t pgn);
        
    private:
        MCP2515* mcp2515;
        uint8_t source_address;
        volatile bool bus_busy;
        uint32_t bus_busy_timeout;
        uint16_t message_size;
        SemaphoreHandle_t bus_state_mutex;
        std::map<uint16_t, MultiFrameMessage> multi_frame_messages;
        std::map<uint16_t, bool> active_bam_sessions;
    };

} // namespace J1939