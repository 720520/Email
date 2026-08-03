from datetime import UTC, datetime

from app.core.config import EmailSettings
from app.email import imap_client
from app.email.imap_client import ImapMailboxGateway


class FakeImapClient:
    instances: list["FakeImapClient"] = []

    def __init__(self, host, **kwargs) -> None:
        self.host = host
        self.kwargs = kwargs
        self.logged_in_with = None
        self.oauth2_logged_in_with = None
        self.selected_folder = None
        self.search_criteria = None
        self.logged_out = False
        self.instances.append(self)

    def starttls(self, ssl_context) -> None:
        self.starttls_context = ssl_context

    def login(self, username, password) -> None:
        self.logged_in_with = (username, password)

    def oauth2_login(self, username, access_token) -> None:
        self.oauth2_logged_in_with = (username, access_token)

    def select_folder(self, folder, readonly=False):
        self.selected_folder = (folder, readonly)
        return {b"UIDVALIDITY": 98765, b"EXISTS": 128}

    def search(self, criteria):
        self.search_criteria = criteria
        return [2, 7, 4]

    def fetch(self, uids, fields):
        del fields
        uid = uids[0]
        return {
            uid: {
                b"BODY[]": b"Subject: test\r\n\r\nbody",
                b"INTERNALDATE": datetime(2026, 7, 24, tzinfo=UTC),
            }
        }

    def logout(self) -> None:
        self.logged_out = True

    def shutdown(self) -> None:
        pass


def test_imap_gateway_connects_readonly_searches_uid_and_fetches_without_seen(
    monkeypatch,
) -> None:
    FakeImapClient.instances.clear()
    monkeypatch.setattr(imap_client, "IMAPClient", FakeImapClient)
    settings = EmailSettings(
        host="imap.example.com",
        username="operations@example.com",
        password="authorization-code",
        folder="基金净值",
        max_messages_per_run=2,
    )

    with ImapMailboxGateway(settings) as gateway:
        uids = gateway.search_uids()
        message = gateway.fetch_message(7)

    client = FakeImapClient.instances[0]
    assert client.kwargs["ssl"] is True
    assert client.kwargs["use_uid"] is True
    assert client.logged_in_with == ("operations@example.com", "authorization-code")
    assert client.selected_folder == ("基金净值", True)
    assert gateway.uid_validity == "98765"
    assert gateway.message_count == 128
    assert client.search_criteria[0] == "SINCE"
    assert uids == [7, 4]
    assert message.uid == 7
    assert message.raw_message.endswith(b"body")
    assert client.logged_out is True


def test_imap_gateway_supports_outlook_oauth2(monkeypatch) -> None:
    FakeImapClient.instances.clear()
    monkeypatch.setattr(imap_client, "IMAPClient", FakeImapClient)
    settings = EmailSettings(
        host="outlook.example.com",
        username="operations@example.com",
        auth_mode="oauth2",
        oauth2_access_token="short-lived-token",
    )

    with ImapMailboxGateway(settings):
        pass

    client = FakeImapClient.instances[0]
    assert client.oauth2_logged_in_with == ("operations@example.com", "short-lived-token")
    assert client.logged_in_with is None
