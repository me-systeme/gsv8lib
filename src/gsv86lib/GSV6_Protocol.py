# -*- coding: utf-8 -*-
__author__ = 'Dennis Rump'
###############################################################################
#
# The MIT License (MIT)
#
# Copyright (c) 2015 Dennis Rump
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
#
# Hiermit wird unentgeltlich, jeder Person, die eine Kopie der Software
# und der zugehörigen Dokumentationen (die "Software") erhält, die
# Erlaubnis erteilt, uneingeschränkt zu benutzen, inklusive und ohne
# Ausnahme, dem Recht, sie zu verwenden, kopieren, ändern, fusionieren,
# verlegen, verbreiten, unter-lizenzieren und/oder zu verkaufen, und
# Personen, die diese Software erhalten, diese Rechte zu geben, unter
# den folgenden Bedingungen:
#
# Der obige Urheberrechtsvermerk und dieser Erlaubnisvermerk sind in
# alle Kopien oder Teilkopien der Software beizulegen.
#
# DIE SOFTWARE WIRD OHNE JEDE AUSDRÜCKLICHE ODER IMPLIZIERTE GARANTIE
# BEREITGESTELLT, EINSCHLIESSLICH DER GARANTIE ZUR BENUTZUNG FÜR DEN
# VORGESEHENEN ODER EINEM BESTIMMTEN ZWECK SOWIE JEGLICHER
# RECHTSVERLETZUNG, JEDOCH NICHT DARAUF BESCHRÄNKT. IN KEINEM FALL SIND
# DIE AUTOREN ODER COPYRIGHTINHABER FÜR JEGLICHEN SCHADEN ODER SONSTIGE
# ANSPRUCH HAFTBAR ZU MACHEN, OB INFOLGE DER ERFÜLLUNG VON EINEM
# VERTRAG, EINEM DELIKT ODER ANDERS IM ZUSAMMENHANG MIT DER BENUTZUNG
# ODER SONSTIGE VERWENDUNG DER SOFTWARE ENTSTANDEN.
#
###############################################################################

import logging
from queue import Full
from . import GSV6_BasicFrameType
from . import GSV6_ErrorCodes
import threading


# from twisted.internet import protocol


# class GSV_6Protocol(protocol.Protocol):
class GSV_6Protocol():
    inDataBuffer = {}
    serialWrite_lock = threading.Lock()

    def connectionLost(self, reason):
        pass

    def __init__(self, frameQueue, anfrageQueue):
        self.inDataBuffer = bytearray()
        self.frameQueue = frameQueue
        self.anfrageQueue = anfrageQueue
        self._log = logging.getLogger('gsv8.GSV_6Protocol')

    def dataReceived(self, data):
        self.inDataBuffer.extend(data)
        if self._log.isEnabledFor(logging.DEBUG):
            self._log.debug('data received: ' + ' '.join(format(x, '02x') for x in bytearray(data)))
        self.checkForCompleteFrame()

    def checkForCompleteFrame(self):
        """
        Iterative Version: sucht in self.inDataBuffer nach vollständigen Frames
        und legt sie in frameQueue ab, solange vollständige Frames vorhanden sind.
        """
        prev_length = -1

        while True:
            # drop all bytes to find sync byte 0xAA
            while (len(self.inDataBuffer) > 0) and (self.inDataBuffer[0] != 0xAA):
                self.inDataBuffer.pop(0)
                if self._log.isEnabledFor(logging.DEBUG):
                    self._log.debug('Drop Byte.')

            # min length messwert = 5 Byte
            # min length antwort  = 4 Byte
            # abort if not enough data received
            if len(self.inDataBuffer) < 4:
                if self._log.isEnabledFor(logging.DEBUG):
                    self._log.debug('return, because minimal FrameLength not reached.')
                    self._log.debug('[rec] no more rec')
                return

            # Falls sich die Länge des Buffers nicht mehr ändert,
            # bringt weiteres Parsen nichts mehr -> Abbruch, um Endlosschleifen zu vermeiden
            current_length = len(self.inDataBuffer)
            if current_length == prev_length:
                if self._log.isEnabledFor(logging.DEBUG):
                    self._log.debug('[rec] no more rec (length unchanged)')
                return
            prev_length = current_length

            state = 0
            counter = 0
            frametype = 0
            payloadLength = 0
            foundcompleteframe = False
            tempArray = bytearray()

            # State-Machine wie bisher, nur ohne Rekursion
            for b in self.inDataBuffer:
                tempArray.append(b)
                counter += 1
                if self._log.isEnabledFor(logging.DEBUG):
                    self._log.debug('State: ' + str(state))

                if state == 0:
                    # okay we strip sync bytes 0xAA and 0x85 in this function
                    # strip 0xAA in state 0
                    del tempArray[-1]

                    # next state
                    state = 1

                elif state == 1:
                    # check FrameType, Interface and length/channels -> state=2
                    # if AntwortFrame or MessFrame?
                    if not (((b & 0xC0) == 0x40) or ((b & 0xC0) == 0x00)):
                        # in this scope we can't pop (del) first byte -> idea: blank the 0xAA
                        self.inDataBuffer[0] = 0x00
                        if self._log.isEnabledFor(logging.DEBUG):
                            self._log.debug('[break] Frame seems to be not a Antwort or MsessFrame.')
                        break
                    else:
                        frametype = int(b >> 6)
                    # if Interface== Serial?
                    if not (b & 0x30 == 0x10):
                        # in this scope we can't pop (del) first byte -> idea: blank the 0xAA
                        self.inDataBuffer[0] = 0x00
                        if self._log.isEnabledFor(logging.DEBUG):
                            self._log.debug('[break] Interface != Serial')
                        break
                    # payloadLength for AntwortFrame or count of Channels for Messframe
                    payloadLength = int(b & 0x0F)
                    if self._log.isEnabledFor(logging.DEBUG):
                        self._log.debug('payloadLength=' + str(payloadLength))
                    state = 2
                    # if not -> drop: state=0;counter=0;drop incommingDataBuffer.pop(0), tempArray=[]

                elif state == 2:
                    # check status byte Mess=indicator; AntwortFrame = in listErrorList?; payloadLength=calculate length of expected payload -> state=3
                    if frametype == 0:
                        if self._log.isEnabledFor(logging.DEBUG):
                            self._log.debug('detected MessFrame')
                        # it's a MessFrame
                        # first check Indikator==1
                        if (b & 0x80) != 0x80:
                            # in this scope we can't pop (del) first byte -> idea: blank the 0xAA
                            self.inDataBuffer[0] = 0x00
                            if self._log.isEnabledFor(logging.DEBUG):
                                self._log.debug('[break] Indikator!=1')
                            break
                        # now get datatype as multiplier for payloadLength
                        multiplier = int((b & 0x70) >> 4) + 1
                        if self._log.isEnabledFor(logging.DEBUG):
                            self._log.debug('multiplier: ' + str(multiplier))
                        # start count at 0-> +1
                        payloadLength += 1
                        payloadLength *= multiplier
                        if self._log.isEnabledFor(logging.DEBUG):
                            self._log.debug('payloadLength: ' + str(payloadLength))
                        state = 3
                    elif frametype == 1:
                        if self._log.isEnabledFor(logging.DEBUG):
                            self._log.debug('detected Antwort Frame')
                        # it's a AntwortFrame
                        # check if errorcode is in the list
                        if b not in GSV6_ErrorCodes.error_code_to_error_shortcut:
                            # in this scope we can't pop (del) first byte -> idea: blank the 0xAA
                            self.inDataBuffer[0] = 0x00
                            if self._log.isEnabledFor(logging.DEBUG):
                                self._log.debug("[break] can't find errorcode ins list.")
                            break
                        else:
                            # if no payload there, stepover state3
                            if payloadLength > 0:
                                state = 3
                            else:
                                state = 4
                    else:
                        # any other frametype is not allow: drop
                        # in this scope we can't pop (del) first byte -> idea: blank the 0xAA
                        self.inDataBuffer[0] = 0x00
                        if self._log.isEnabledFor(logging.DEBUG):
                            self._log.debug('[break] other FrameType detected.')
                        break
                        # if not -> drop: state=0;counter=0;drop incommingDataBuffer.pop(0), tempArray=[]
                        # if payload>6*4Byte, drop also

                elif state == 3:
                    if self._log.isEnabledFor(logging.DEBUG):
                        self._log.debug('counter-state: ' + str((counter - state)))
                    if payloadLength == (counter - state):
                        state = 4
                        # so we got the whole payload goto state=4

                elif state == 4:
                    # at the first time in state 4, we have to break
                    # if b== 0x85 -> we have a complete Frame; pushback the complete Frame and remove copied bytes from incomingBuffer and break For-Loop
                    if not (b == 0x85):
                        # in this scope we can't pop (del) first byte -> idea: blank the 0xAA
                        self.inDataBuffer[0] = 0x00
                        if self._log.isEnabledFor(logging.DEBUG):
                            self._log.debug("[break] can't find 0x85")
                    else:
                        if self._log.isEnabledFor(logging.DEBUG):
                            self._log.debug('[break] found an complete Frame')
                        foundcompleteframe = True

                        # okay we strip sync bytes 0xAA and 0x85 in this function
                        # strip 0x85 in state 4
                        del tempArray[-1]

                        frame = GSV6_BasicFrameType.BasicFrame(tempArray)
                        try:
                            self.frameQueue.put_nowait(frame)
                        except Full:
                            if self._log.isEnabledFor(logging.WARNING):
                                self._log.warning('a complete Frame was droped, because Queue was full')
                        if self._log.isEnabledFor(logging.DEBUG):
                            self._log.debug('[serial] Received complete Frame: ' +
                            ' '.join(format(x, '02x') for x in bytearray(tempArray)))

                    # break anyway
                    break

            # Ende des for-Loops über inDataBuffer

            if foundcompleteframe:
                # remove copied items
                # (Original: self.inDataBuffer[0:counter - 1] = [])
                self.inDataBuffer[0:counter - 1] = []
                if self._log.isEnabledFor(logging.DEBUG):
                    self._log.debug('new inDataBuffer[0]: ' +
                    ' '.join(format(self.inDataBuffer[0], '02x')))

                # Danach weiter im while-Loop -> nächstes Frame suchen
                if self._log.isEnabledFor(logging.DEBUG):
                    self._log.debug('[rec] start rec (loop)')
                continue
            else:
                # Kein vollständiges Frame gefunden oder Fehler -> nichts entfernt,
                # also macht weiteres Parsen jetzt keinen Sinn.
                if self._log.isEnabledFor(logging.DEBUG):
                    self._log.debug('[rec] no more rec (no complete frame)')
                return


    def addToWriteQueue(self, data):
        pass

    def write(self, data):
        self.serialWrite_lock.acquire()
        self.transport.write(data)
        self.serialWrite_lock.release()
