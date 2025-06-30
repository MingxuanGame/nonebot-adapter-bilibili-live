from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
import json
import struct
from typing import Any
import zlib

import brotli


class ProtocolVersion(IntEnum):
    Normal = 0
    Heartbeat = 1
    Zlib = 2
    Brotli = 3


class OpCode(IntEnum):
    Heartbeat = 2
    HeartbeatReply = 3
    Auth = 7
    AuthReply = 8
    Command = 5


HEADER_LENGTH = 16


@dataclass
class Packet:
    length: int
    header_length: int
    protocol_version: ProtocolVersion
    opcode: OpCode
    seq: int
    data: bytes

    @classmethod
    def new(
        cls,
        opcode: OpCode,
        seq: int,
        data: dict[str, Any],
        protocol_version: ProtocolVersion = ProtocolVersion.Normal,
    ) -> "Packet":
        """Create a new packet instance."""
        raw = json.dumps(data).encode("utf-8")
        return cls(
            length=len(raw) + HEADER_LENGTH,
            header_length=HEADER_LENGTH,
            protocol_version=protocol_version,
            opcode=opcode,
            seq=seq,
            data=raw,
        )

    @classmethod
    def new_binary(
        cls,
        opcode: OpCode,
        seq: int,
        data: bytes,
        protocol_version: ProtocolVersion = ProtocolVersion.Normal,
    ) -> "Packet":
        """Create a new packet instance with binary data."""
        return cls(
            length=len(data) + HEADER_LENGTH,
            header_length=HEADER_LENGTH,
            protocol_version=protocol_version,
            opcode=opcode,
            seq=seq,
            data=data,
        )

    def to_bytes(self) -> bytes:
        header = struct.pack(
            ">I2H2I",
            self.length,
            self.header_length,
            self.protocol_version.value,
            self.opcode.value,
            self.seq,
        )
        return header + self.data

    @classmethod
    def from_bytes(cls, payload: bytes) -> "Packet":
        if len(payload) < HEADER_LENGTH:
            raise ValueError("Data too short to be a valid packet")
        (
            length,
            header_length,
            protocol_version,
            opcode,
            seq,
        ) = struct.unpack(">I2H2I", payload[:HEADER_LENGTH])
        protocol_version = ProtocolVersion(protocol_version)
        if protocol_version not in ProtocolVersion:
            raise ValueError(f"Unsupported protocol version: {protocol_version}")

        return cls(
            length=length,
            header_length=header_length,
            protocol_version=ProtocolVersion(protocol_version),
            opcode=OpCode(opcode),
            seq=seq,
            data=payload[HEADER_LENGTH:length],
        )

    def decode_data(self) -> dict[str, Any] | list["Packet"]:
        """Decode the data field of the packet."""
        if self.protocol_version == ProtocolVersion.Zlib:
            decompressed = zlib.decompress(self.data)
            return self._parse_multiple_packets(decompressed)
        elif self.protocol_version == ProtocolVersion.Brotli:
            decompressed = brotli.decompress(self.data)
            return self._parse_multiple_packets(decompressed)
        elif self.opcode == OpCode.HeartbeatReply:
            return {
                "popularity": int.from_bytes(self.data[0:4], "big"),
                "payload": self.data[4:],
            }
        else:
            return json.loads(self.data.decode("utf-8"))

    def decode_dict(self) -> dict[str, Any]:
        d = self.decode_data()
        assert isinstance(d, dict), "Decoded data is not a dictionary"
        return d

    def _parse_multiple_packets(self, data: bytes) -> list["Packet"]:
        """Parse multiple packets from decompressed data."""
        packets = []
        offset = 0

        while offset < len(data):
            if len(data) - offset < HEADER_LENGTH:
                break

            # Parse packet header
            (
                length,
                header_length,
                protocol_version,
                opcode,
                seq,
            ) = struct.unpack(">I2H2I", data[offset : offset + HEADER_LENGTH])

            # Extract packet data
            packet_data = data[offset + HEADER_LENGTH : offset + length]

            # Create packet
            packet = Packet(
                length=length,
                header_length=header_length,
                protocol_version=ProtocolVersion(protocol_version),
                opcode=OpCode(opcode),
                seq=seq,
                data=packet_data,
            )

            packets.append(packet)
            offset += length

        return packets


def new_auth_packet(room_id: int, uid: int, token: str, buvid3: str) -> Packet:
    data = {
        "uid": uid,
        "roomid": room_id,
        "protover": 3,
        "buvid": buvid3,
        "platform": "web",
        "type": 2,
        "key": token,
    }
    return Packet.new(OpCode.Auth, 1, data, ProtocolVersion.Heartbeat)
