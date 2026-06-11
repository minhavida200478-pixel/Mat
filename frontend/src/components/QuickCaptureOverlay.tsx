// Quick Capture Overlay - Integrates FAB with Bottom Sheets
import React, { useRef, useCallback, useState } from 'react';
import { StyleSheet, View } from 'react-native';
import { useRouter } from 'expo-router';

import FAB from './FAB';
import {
  WaterSheet, WaterSheetRef,
  MealSheet, MealSheetRef,
  MedicationSheet, MedicationSheetRef,
  ActivitySheet, ActivitySheetRef,
  MoodSheet, MoodSheetRef,
  SymptomSheet, SymptomSheetRef,
  NoteSheet, NoteSheetRef,
} from './BottomSheet';

type Props = {
  onEventLogged?: (eventType: string) => void;
  visible?: boolean;
};

export default function QuickCaptureOverlay({ onEventLogged, visible = true }: Props) {
  const router = useRouter();
  const [fabVisible, setFabVisible] = useState(visible);
  
  // Sheet refs
  const waterRef = useRef<WaterSheetRef>(null);
  const mealRef = useRef<MealSheetRef>(null);
  const medicationRef = useRef<MedicationSheetRef>(null);
  const activityRef = useRef<ActivitySheetRef>(null);
  const moodRef = useRef<MoodSheetRef>(null);
  const symptomRef = useRef<SymptomSheetRef>(null);
  const noteRef = useRef<NoteSheetRef>(null);

  const handleAction = useCallback((action: string) => {
    switch (action) {
      case 'water':
        waterRef.current?.open();
        break;
      case 'meal':
        mealRef.current?.open();
        break;
      case 'medication':
        medicationRef.current?.open();
        break;
      case 'activity':
        activityRef.current?.open();
        break;
      case 'mood':
        moodRef.current?.open();
        break;
      case 'symptom':
        symptomRef.current?.open();
        break;
      case 'note':
        noteRef.current?.open();
        break;
      default:
        // Fallback to log page for complex actions
        router.push(`/log?focus=${action}`);
    }
  }, [router]);

  const handleSuccess = useCallback((eventType: string) => {
    onEventLogged?.(eventType);
  }, [onEventLogged]);

  return (
    <>
      <FAB onAction={handleAction} visible={fabVisible} />
      
      {/* Bottom Sheets */}
      <WaterSheet ref={waterRef} onSuccess={() => handleSuccess('water')} />
      <MealSheet ref={mealRef} onSuccess={() => handleSuccess('meal')} />
      <MedicationSheet ref={medicationRef} onSuccess={() => handleSuccess('medication')} />
      <ActivitySheet ref={activityRef} onSuccess={() => handleSuccess('activity')} />
      <MoodSheet ref={moodRef} onSuccess={() => handleSuccess('mood')} />
      <SymptomSheet ref={symptomRef} onSuccess={() => handleSuccess('symptom')} />
      <NoteSheet ref={noteRef} onSuccess={() => handleSuccess('note')} />
    </>
  );
}

const styles = StyleSheet.create({});
