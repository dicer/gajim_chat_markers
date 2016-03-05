# -*- coding:utf-8 -*-

import collections
import nbxmpp
from common import gajim, ged
from plugins import GajimPlugin


class ChatMarkersPlugin(GajimPlugin):

    CHAT_MARKERS_NS= "urn:xmpp:chat-markers:0"

    last_markable = {}
    last_send = {}
    mark = {}
    textviews = {}
    handlers = []

    def init(self):
        self.events_handlers = {
            "stanza-message-outgoing": (ged.OUT_PRECORE, self.on_outgoing_msg_stanza),
            "message-outgoing": (ged.OUT_PRECORE, self.on_message_outgoing),
            "raw-message-received": (ged.OUT_PRECORE, self.on_incoming_msg_stanza),
            "decrypted-message-received": (ged.OUT_PRECORE, self.on_decrypted_message_reveived)
        }
        self.gui_extension_points = {
            'chat_control_base': (self.on_connect_with_chat_control, self.on_disconnect_from_chat_control)
        }

    def on_decrypted_message_reveived(self, event):
        self.remove_mark(event.jid)

    def on_message_outgoing(self, event):
        if event.jid in self.textviews and self.textviews[event.jid] !=event.control.conv_textview.tv:
            self.reset_jid(event.jid)
        if event.jid not in self.textviews:
            self.textviews[event.jid] = event.control.conv_textview.tv

        function = event.callback
        def new_callback(*args, **kwargs):
            function_result = function(*args, **kwargs)
            if event.jid not in self.last_send:
                self.last_send[event.jid] = collections.deque(maxlen=5)
            mark = self.textviews[event.jid].get_buffer().create_mark(None, self.textviews[event.jid].get_buffer().get_end_iter(), left_gravity=True)
            self.last_send[event.jid].append((args[0].getID(), mark))
            return function_result

        if event.callback:
            event.callback = new_callback
        return False

    def on_outgoing_msg_stanza(self, event):
        if event.msg_iq.getBody():
            event.msg_iq.addChild(name="markable", namespace=self.CHAT_MARKERS_NS)
        return False

    def on_incoming_msg_stanza(self, event):
        children = event.stanza.getChildren()
        for child in children:
            if child.getNamespace() == self.CHAT_MARKERS_NS:
                jid = event.stanza.getFrom().getStripped()
                if child.getName() == "displayed":
                    self.update_mark(jid, child.getAttr("id"))
                elif child.getName() == "markable":
                    self.last_markable[jid] = event.stanza
                break
        return False

    def on_seen(self, jid, account):
        self.send_displayed(jid, account)

    def on_connect_with_chat_control(outerself, control):

        class WindowHandler(object):

            def __init__(self, parent_win):
                self.message_window = parent_win
                self.notebook_page = None

                self.focus_in_handler_id = parent_win.window.connect('focus-in-event', self.on_window_focus_in)
                self.focus_out_handler_id = parent_win.window.connect('focus-out-event', self.on_window_focus_out)
                self.switch_page_handler_id = parent_win.notebook.connect('switch-page', self.on_notebook_switch_page)

            def __del__(self):
                self.message_window.window.disconnect(self.focus_in_handler_id)
                self.message_window.window.disconnect(self.focus_out_handler_id)
                self.message_window.notebook.disconnect(self.switch_page_handler_id)

            def on_notebook_switch_page(self, notebook, page, page_num):
                active_ctrl_old = self.get_control()
                if active_ctrl_old:
                    outerself.on_seen(active_ctrl_old.contact.jid, active_ctrl_old.account)
                self.notebook_page = notebook.get_nth_page(page_num)
                active_ctrl_new = self.get_control()
                outerself.on_seen(active_ctrl_new.contact.jid, active_ctrl_new.account)

            def on_window_focus_in(self, widget, event):
                self.notebook_page = self.message_window.notebook.get_nth_page(self.message_window.notebook.get_current_page())
                active_ctrl = self.get_control()
                if active_ctrl:
                    outerself.on_seen(active_ctrl.contact.jid, active_ctrl.account)

            def on_window_focus_out(self, widget, event):
                active_ctrl = self.get_control()
                if active_ctrl:
                    outerself.on_seen(active_ctrl.contact.jid, active_ctrl.account)

            def get_control(self):
                return self.message_window._widget_to_control(self.notebook_page)

        if not any([window_handler.message_window for window_handler in outerself.handlers]):
            outerself.handlers.append(WindowHandler(control.parent_win))

    def on_disconnect_from_chat_control(self, control):
        pass

    def update_mark(self, jid, at_id_new):
        if jid in self.last_send:
            for msg_id, buffer_mark in self.last_send[jid]:
                if msg_id == at_id_new:
                    if jid in self.mark:
                        self.remove_mark(jid)
                    self.add_mark(jid, buffer_mark)

    def remove_mark(self, jid):
        if jid in self.textviews and jid in self.mark:
            buffer_iter = self.textviews[jid].get_buffer().get_iter_at_mark(self.mark[jid])
            buffer_iter.forward_line()
            buffer_iter_end = buffer_iter.copy()
            buffer_iter_end.forward_chars(2)
            self.textviews[jid].get_buffer().delete(buffer_iter, buffer_iter_end)
            self.mark.pop(jid, None)

    def add_mark(self, jid, buffer_mark):
        buffer_iter = self.textviews[jid].get_buffer().get_iter_at_mark(buffer_mark)
        buffer_iter.forward_line()
        self.textviews[jid].get_buffer().insert(buffer_iter, unicode('\n👀'))
        self.mark[jid] = buffer_mark

    def reset_jid(self, jid):
        self.textviews.pop(jid, None)
        self.last_markable.pop(jid, None)
        self.mark.pop(jid, None)
        self.last_send.pop(jid, None)

    def send_displayed(self, jid, account):
        stanza_rec = self.last_markable.pop(jid, None)
        if stanza_rec:
            stanza_send = nbxmpp.Message(to=stanza_rec.getFrom(), typ='chat')
            stanza_send.addChild("displayed", namespace=self.CHAT_MARKERS_NS, attrs={'id': stanza_rec.getID()})
            gajim.connections[account].connection.send(stanza_send, now=True)