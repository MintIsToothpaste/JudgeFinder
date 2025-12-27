import org.jetbrains.compose.desktop.application.dsl.TargetFormat

plugins {
    kotlin("multiplatform") version "2.0.0"
    id("org.jetbrains.compose") version "1.6.11"
    id("org.jetbrains.kotlin.plugin.compose") version "2.0.0-RC2"
    id("app.cash.sqldelight") version "2.0.2"
}

kotlin {
    jvm("desktop") {
        withJava()
        compilations.all {
            kotlinOptions.jvmTarget = "17"
        }
    }

    sourceSets {
        val commonMain by getting {
            dependencies {
                implementation(compose.runtime)
                implementation(compose.material3)
                implementation(compose.foundation)
                implementation("org.jetbrains.kotlinx:kotlinx-datetime:0.6.0")
                implementation("app.cash.sqldelight:runtime:2.0.2")
                implementation("io.ktor:ktor-client-core:2.3.11")
            }
        }
        val commonTest by getting
        val desktopMain by getting {
            dependencies {
                implementation(compose.desktop.currentOs)
                implementation("app.cash.sqldelight:sqlite-driver:2.0.2")
                implementation("io.ktor:ktor-client-cio:2.3.11")
                implementation("org.jsoup:jsoup:1.17.2")
            }
        }
        val desktopTest by getting
    }
}

compose.desktop {
    application {
        mainClass = "com.judgefinder.app.MainKt"
        nativeDistributions {
            targetFormats(TargetFormat.Dmg, TargetFormat.Msi, TargetFormat.Deb)
            packageName = "JudgeFinder"
            packageVersion = "1.0.0"
        }
    }
}

sqldelight {
    databases {
        create("NoticeDatabase") {
            packageName.set("com.judgefinder.db")
            schemaOutputDirectory.set(file("src/commonMain/sqldelight/databases"))
        }
    }
}
