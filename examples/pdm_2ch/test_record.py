import os
import sys
from threading import Thread, Lock

import serial
import numpy as np
import soundfile as sf
from serial.tools import list_ports

def get_nrf():
    ports = list_ports.comports()
    for port in ports:
        if sys.platform == 'win32':
            match = port.pid == 32837
        else:
            match = 'nRF52840' in port.description
        if match:
            print(f'Detected nRF on {port.device}')
            return port.device
    raise RuntimeError('Cannot find nRF')


class SerialAudioPacketParser:
    def __init__(self):
        self.buf = bytearray()

    def add_data(self, data):
        self.buf.extend(data)

    def parse_packet(self):
        start_marker = b'\x00\x11\x22\x33'
        minimum_packet_size = 5000
        # ------------------------- Packet -------------------------
        # 0  | 1  | 2  | 3  | 4 ... 5                 | 6 ... 6+len
        # 00 | 11 | 22 | 33 | Payload Length (uint16) |  Payload
        # ----------------------------------------------------------
        decoded = []
        while len(self.buf) > minimum_packet_size:
            if self.buf[0:4] == start_marker:
                payload_len = int.from_bytes(self.buf[4:6], byteorder='big', signed=False)
                data_start = 6
                data_end = payload_len * 2 + 6
                data = np.ndarray(shape=(payload_len,), dtype='int16',
                                  buffer=self.buf[data_start:data_end])
                decoded.append(data)
                self.buf = self.buf[data_end:]
            else:
                pak_start = bytearray(self.buf).find(start_marker)
                assert pak_start != 0, "This should've been handled by if statement above!"
                assert pak_start != -1, "Start marker not found in buffer! Is the minimum_packet_size too small?"
                # Drop everything before start_marker
                print(f'Dropped {pak_start} bytes before start marker')
                self.buf = self.buf[pak_start:]
                continue
        return decoded

class SerialAudioRecorder(Thread):
    def __init__(self, port):
        self.port = port
        self.serial = serial.Serial(self.port, 115200)
        self.serial.reset_input_buffer()
        self.parser = SerialAudioPacketParser()
        self.stopped = False
        self.savelock = Lock()
        print(f'Opening {self.port}...')
        Thread.__init__(self)

    def run(self):
        while not self.stopped:
            parsed = []
            while len(parsed) == 0:
                self.parser.add_data(self.serial.read(1000))
                parsed = self.parser.parse_packet()
            self.parse_audio(parsed)
        self.close()

    def stop(self):
        self.stopped = True

    def savefile(self, filename):
        self.savelock.acquire()
        self.do_savefile(filename)
        self.savelock.release()

    def do_savefile(self, filename):
        raise NotImplementedError('Please implement do_savefile() in subclass!')

    def parse_audio(self, packets):
        self.savelock.acquire()
        self.do_parse_audio(packets)
        self.savelock.release()

    def do_parse_audio(self, packets):
        raise NotImplementedError('Please implement do_parse_audio in subclass!')

    def clear(self):
        self.savelock.acquire()
        self.do_clear()
        self.savelock.release()

    def do_clear(self):
        raise NotImplementedError('Please implement do_clear() in subclass!')

    def close(self):
        print(f'Closing {self.port}...')
        self.serial.close()


class BCMRecorder(SerialAudioRecorder):
    def __init__(self):
        self.buffer = {
            'mic': [],
            'bcm': []
        }
        super().__init__(get_nrf())

    def do_parse_audio(self, packets):
        for packet in packets:
            mic_samples = packet[::2]
            bcm_samples = packet[1::2]
            assert len(mic_samples) == len(bcm_samples)
            self.buffer['mic'].append(mic_samples)
            self.buffer['bcm'].append(bcm_samples)

    def do_savefile(self, filename):
        gt_filename = f'{filename}_gt.wav'
        data_filename = f'{filename}_data.wav'
        for file in [gt_filename, data_filename]:
            if os.path.exists(file):
                os.remove(file)
        mic_data = np.concatenate(self.buffer['mic'])
        bcm_data = np.concatenate(self.buffer['bcm'])
        sf.write(gt_filename, mic_data, 16000, format='wav')
        sf.write(data_filename, bcm_data, 16000, format='wav')
        n_samples = len(mic_data)
        print(f'[BCM] {n_samples} samples -> {n_samples / 16000:.2f} seconds saved')
        self.do_clear()

    def do_clear(self):
        self.buffer = {
            'mic': [],
            'bcm': []
        }


if __name__ == '__main__':
    rec = BCMRecorder()
    fname = input('Enter filename: ')
    rec.start()
    while True:
        try:
            choice = input('Enter to save recording, r to re-record, ctrl+c to stop\n')
            if choice == 'r':
                rec.clear()
                continue
            else:
                rec.savefile(fname)
                break
        except KeyboardInterrupt:
            break
    rec.stop()
    rec.join()
