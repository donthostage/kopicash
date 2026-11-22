import unittest
from pathlib import Path


PAGE = Path(__file__).with_name('wallet.html').read_text(encoding='utf-8')


class WalletPage(unittest.TestCase):
    def test_home_only_promotes_comparison(self):
        hero = PAGE.split('<section class="hero', 1)[1].split('</section>', 1)[0]
        self.assertIn('Какой картой выгоднее заплатить?', hero)
        self.assertIn('>Сравнить карты<', hero)
        comparison = hero.split('<section class="home-wallet"', 1)[0]
        self.assertEqual(comparison.count('<button'), 1)
        self.assertIn('id="homeCarousel"', hero)
        self.assertNotIn('id="homePreview"', PAGE)
        self.assertNotIn('pocket.webp', PAGE)

    def test_wallet_navigation_matches_the_visible_sections(self):
        nav = PAGE.split('<nav class="wallet-nav"', 1)[1].split('</nav>', 1)[0]
        buttons = ('openHome', 'openCashback', 'openCards', 'openProfile')
        self.assertEqual(nav.count('<button'), len(buttons))
        self.assertEqual(sorted(buttons, key=lambda item: nav.index(f'id="{item}"')), list(buttons))
        self.assertNotIn('>Назад</button>', PAGE)
        for key in ('cashbackPanel', 'historyPanel', 'buyPanel', 'cardsPanel', 'accountPanel',
                    'bankSearch', 'addSource', 'deleteDialog', 'openCatalog', 'nextCard', 'previousCard'):
            self.assertIn(f'id="{key}"', PAGE)

    def test_cashback_and_profile_have_separate_actions(self):
        profile, cashback = PAGE.split('id="accountPanel"', 1)[1].split('id="cashbackPanel"', 1)
        for key in ('accountAvatar', 'settingsUser', 'logout', 'accountStats'):
            self.assertIn(f'id="{key}"', profile)
        for key in ('homeMonthCashback', 'openPlan', 'showStatsBtn', 'purchasePlan'):
            self.assertIn(f'id="{key}"', cashback)
        header = PAGE.split('<header class="topbar">', 1)[1].split('</header>', 1)[0]
        self.assertLess(header.index('id="themeToggle"'), header.index('id="settingsOpen"'))
        self.assertIn('id="passwordToggle"', PAGE)

    def test_gallery_pick_reads_bytes(self):
        self.assertIn('accept="image/jpeg,image/png,image/webp"', PAGE)
        self.assertIn('id="shotPrivacy"', PAGE)
        self.assertNotIn('readAsDataURL', PAGE)
        self.assertIn('file.slice', PAGE)

    def test_app_starts_hidden_behind_welcome(self):
        self.assertIn('id="appScreen" hidden', PAGE)
        self.assertIn('id="welcomeScreen"', PAGE)

    def test_wallet_loads_checkout_and_cashback_scripts(self):
        self.assertIn('id="buyAmount"', PAGE)
        self.assertIn('/static/wallet-shell.js', PAGE)
        self.assertIn('href="/static/wallet-shell.css', PAGE)
        self.assertIn('src="/wallet-cashback.js?', PAGE)
        self.assertIn("defineProperty(window,name", PAGE)
        self.assertIn('function apiErrorText', PAGE)
        self.assertIn('API_CODE_TEXT', PAGE)

    def test_card_arc_uses_pointer_swipe_and_keyboard(self):
        self.assertIn('id="cardCarousel"', PAGE)
        self.assertIn('carousel-fan.js', PAGE)
        fan_js = Path(__file__).with_name('static').joinpath('carousel-fan.js').read_text(encoding='utf-8')
        self.assertIn('carouselTap', fan_js)
        self.assertIn("addEventListener('click'", fan_js)
        self.assertIn('pointerdown', fan_js)
        self.assertIn('pointermove', fan_js)
        self.assertIn('ArrowLeft', fan_js)
        self.assertIn('ArrowRight', fan_js)
        self.assertIn('prefers-reduced-motion: reduce', fan_js)
        self.assertIn('BEHIND_EDGE', fan_js)
        self.assertIn('id="demoBar"', PAGE)
        self.assertIn('demo=cards', PAGE)
        self.assertIn('id="homeCarouselPosition"', PAGE)

    def test_card_arc_keeps_empty_state_and_bank_colors(self):
        self.assertIn('Кошелёк пуст', PAGE)
        self.assertIn('carouselCardPaint', PAGE)
        self.assertIn('--carousel-glow', PAGE)
        self.assertIn('id="walletEmpty"', PAGE)
