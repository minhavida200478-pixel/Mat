// Floating Action Button with quick actions menu
import React, { useState, useRef, useCallback } from 'react';
import {
  StyleSheet,
  TouchableOpacity,
  View,
  Text,
  Animated,
  Pressable,
  Platform,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import * as Haptics from 'expo-haptics';

import { colors, radius, spacing, type } from '@/src/theme';

export type QuickAction = {
  key: string;
  label: string;
  icon: string;
  color: string;
};

const QUICK_ACTIONS: QuickAction[] = [
  { key: 'water', label: 'Water', icon: 'water', color: '#4A90D9' },
  { key: 'meal', label: 'Meal', icon: 'restaurant', color: '#E67E22' },
  { key: 'medication', label: 'Medication', icon: 'medical', color: '#9B59B6' },
  { key: 'symptom', label: 'Symptom', icon: 'pulse', color: colors.brand.primary },
  { key: 'mood', label: 'Mood', icon: 'happy', color: colors.status.fertile },
  { key: 'activity', label: 'Activity', icon: 'heart', color: '#E91E63' },
  { key: 'note', label: 'Note', icon: 'create', color: '#607D8B' },
];

type FABProps = {
  onAction: (action: string) => void;
  visible?: boolean;
};

export default function FAB({ onAction, visible = true }: FABProps) {
  const insets = useSafeAreaInsets();
  const [expanded, setExpanded] = useState(false);
  const animation = useRef(new Animated.Value(0)).current;

  const toggleMenu = useCallback(() => {
    if (Platform.OS !== 'web') {
      Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    }
    const toValue = expanded ? 0 : 1;
    Animated.spring(animation, {
      toValue,
      friction: 6,
      tension: 40,
      useNativeDriver: true,
    }).start();
    setExpanded(!expanded);
  }, [expanded, animation]);

  const handleAction = useCallback((key: string) => {
    if (Platform.OS !== 'web') {
      Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light);
    }
    toggleMenu();
    onAction(key);
  }, [onAction, toggleMenu]);

  if (!visible) return null;

  const rotation = animation.interpolate({
    inputRange: [0, 1],
    outputRange: ['0deg', '45deg'],
  });

  const overlayOpacity = animation.interpolate({
    inputRange: [0, 1],
    outputRange: [0, 1],
  });

  return (
    <>
      {/* Overlay */}
      {expanded && (
        <Animated.View
          style={[styles.overlay, { opacity: overlayOpacity }]}
        >
          <Pressable style={StyleSheet.absoluteFill} onPress={toggleMenu} />
        </Animated.View>
      )}

      {/* Action buttons */}
      <View style={[styles.container, { bottom: insets.bottom + 90 }]}>
        {QUICK_ACTIONS.map((action, index) => {
          const translateY = animation.interpolate({
            inputRange: [0, 1],
            outputRange: [0, -(index + 1) * 60],
          });
          const scale = animation.interpolate({
            inputRange: [0, 0.5, 1],
            outputRange: [0, 0, 1],
          });
          const opacity = animation.interpolate({
            inputRange: [0, 0.5, 1],
            outputRange: [0, 0, 1],
          });

          return (
            <Animated.View
              key={action.key}
              style={[
                styles.actionItem,
                {
                  transform: [{ translateY }, { scale }],
                  opacity,
                },
              ]}
            >
              <TouchableOpacity
                style={styles.actionLabel}
                onPress={() => handleAction(action.key)}
                activeOpacity={0.7}
              >
                <Text style={styles.actionText}>{action.label}</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={[styles.actionButton, { backgroundColor: action.color }]}
                onPress={() => handleAction(action.key)}
                activeOpacity={0.8}
              >
                <Ionicons name={action.icon as any} size={22} color="#fff" />
              </TouchableOpacity>
            </Animated.View>
          );
        })}

        {/* Main FAB button */}
        <TouchableOpacity
          style={styles.fab}
          onPress={toggleMenu}
          activeOpacity={0.9}
          testID="fab-button"
        >
          <Animated.View style={{ transform: [{ rotate: rotation }] }}>
            <Ionicons name="add" size={32} color="#fff" />
          </Animated.View>
        </TouchableOpacity>
      </View>
    </>
  );
}

const styles = StyleSheet.create({
  overlay: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: 'rgba(0,0,0,0.4)',
    zIndex: 998,
  },
  container: {
    position: 'absolute',
    right: spacing.screen,
    alignItems: 'flex-end',
    zIndex: 999,
  },
  fab: {
    width: 56,
    height: 56,
    borderRadius: 28,
    backgroundColor: colors.brand.primary,
    alignItems: 'center',
    justifyContent: 'center',
    elevation: 8,
    ...Platform.select({
      web: { boxShadow: '0px 4px 8px rgba(0,0,0,0.3)' },
      default: {
        shadowColor: '#000',
        shadowOffset: { width: 0, height: 4 },
        shadowOpacity: 0.3,
        shadowRadius: 8,
      },
    }),
  },
  actionItem: {
    position: 'absolute',
    right: 0,
    flexDirection: 'row',
    alignItems: 'center',
  },
  actionButton: {
    width: 44,
    height: 44,
    borderRadius: 22,
    alignItems: 'center',
    justifyContent: 'center',
    elevation: 4,
    ...Platform.select({
      web: { boxShadow: '0px 2px 4px rgba(0,0,0,0.2)' },
      default: {
        shadowColor: '#000',
        shadowOffset: { width: 0, height: 2 },
        shadowOpacity: 0.2,
        shadowRadius: 4,
      },
    }),
  },
  actionLabel: {
    backgroundColor: '#fff',
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderRadius: radius.sm,
    marginRight: spacing.sm,
    elevation: 2,
    ...Platform.select({
      web: { boxShadow: '0px 1px 2px rgba(0,0,0,0.1)' },
      default: {
        shadowColor: '#000',
        shadowOffset: { width: 0, height: 1 },
        shadowOpacity: 0.1,
        shadowRadius: 2,
      },
    }),
  },
  actionText: {
    ...type.bodySm,
    color: colors.text.primary,
    fontWeight: '600',
  },
});
