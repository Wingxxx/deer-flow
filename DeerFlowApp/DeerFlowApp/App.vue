<script>
	export default {
		onLaunch: function() {
			console.log('[App] onLaunch triggered')
			// #ifdef APP-PLUS
			console.log('[App] Platform:', plus.os.name)
			console.log('[App] OS Version:', plus.os.version)
			console.log('[App] softinputMode:', 'adjustResize (configured in manifest.json)')
			// #endif
		},
		onShow: function() {
			console.log('[App] onShow triggered')
		},
		onHide: function() {
			console.log('[App] onHide triggered')
		}
	}
</script>

<style>
	/*每个页面公共css */
</style>
