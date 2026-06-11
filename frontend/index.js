/**
 * Custom entry point for Android Widget support
 * Registers the widget task handler before loading the Expo Router app
 */

import { Platform } from 'react-native';

// Register Android widget task handler BEFORE importing expo-router
if (Platform.OS === 'android') {
  try {
    const { registerWidgetTaskHandler } = require('react-native-android-widget');
    const { widgetTaskHandler } = require('./src/widgets');
    registerWidgetTaskHandler(widgetTaskHandler);

    // Define + register the periodic background refresh task (keeps widgets fresh
    // without opening the app). Defining happens on import; registration is idempotent.
    const { registerWidgetBackgroundTask } = require('./src/widgets/backgroundTask');
    registerWidgetBackgroundTask();
  } catch (error) {
    // Widget module not available (e.g., in Expo Go)
    console.log('Android widgets not available:', error.message);
  }
}

// Import the default expo-router entry
import 'expo-router/entry';
