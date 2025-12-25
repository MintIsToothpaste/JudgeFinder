package com.judgefinder.app

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.compose.ui.window.ApplicationScope
import androidx.compose.ui.window.Window
import androidx.compose.ui.window.application
import com.judgefinder.di.AppModule
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch

fun main() = application {
    val appModule = AppModule()
    App(appModule, this)
}

@Composable
private fun App(module: AppModule, scope: ApplicationScope) {
    val notices = remember { mutableStateListOf<com.judgefinder.domain.model.Notice>() }
    val status = remember { mutableStateOf("Ready") }
    val coroutineScope = remember { CoroutineScope(Dispatchers.Main) }

    Window(onCloseRequest = { scope.exitApplication() }, title = "JudgeFinder") {
        MaterialTheme {
            Surface(modifier = Modifier.fillMaxSize()) {
                Column(modifier = Modifier.padding(16.dp)) {
                    Button(onClick = {
                        coroutineScope.launch {
                            status.value = "Syncing..."
                            val result = module.syncNoticesUseCase()
                            val latest = module.queryNoticesUseCase()
                            notices.clear()
                            notices.addAll(latest)
                            status.value = "Synced: added=${result.added}, updated=${result.updated}"
                        }
                    }) {
                        Text("Sync")
                    }
                    Text(status.value, modifier = Modifier.padding(vertical = 8.dp))
                    LazyColumn {
                        items(notices) { notice ->
                            Column(modifier = Modifier.padding(vertical = 8.dp)) {
                                Text(notice.normalizedTitle)
                                Text(notice.url)
                            }
                        }
                    }
                }
            }
        }
    }
}
