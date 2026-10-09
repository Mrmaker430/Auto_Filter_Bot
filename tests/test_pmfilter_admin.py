import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

class TestPmFilterAdminExemption(unittest.TestCase):

    def test_admin_pm_text_ignored(self):
        async def run_test():
            from plugins.pmfilter import pm_text

            mock_bot = MagicMock()
            mock_message = MagicMock()
            mock_message.text = "Inception 2010"
            mock_message.from_user.first_name = "AdminUser"
            mock_message.from_user.id = 1773034985  # Present in ADMINS in info.py
            mock_message.react = AsyncMock()

            with patch("database.config_db.mdb.update_top_messages", new_callable=AsyncMock) as mock_update_top, \
                 patch("database.users_chats_db.db.pm_search_status", new_callable=AsyncMock) as mock_pm_search_status:

                await pm_text(mock_bot, mock_message)

                # Expect update_top_messages NOT to be called for admin user
                mock_update_top.assert_not_called()
                mock_pm_search_status.assert_not_called()

        asyncio.run(run_test())

if __name__ == "__main__":
    unittest.main()
