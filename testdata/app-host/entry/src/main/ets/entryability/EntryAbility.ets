import { UIAbility, Want, AbilityConstant } from '@kit.AbilityKit';
import { hilog } from '@kit.PerformanceAnalysisKit';
import { window } from '@kit.ArkUI';
import gohmos from 'libgohmos.so';

// Tests run on a native worker thread, never blocking the ability/UI thread.
export default class EntryAbility extends UIAbility {
  onCreate(want: Want, launchParam: AbilityConstant.LaunchParam): void {
    const token = want.parameters?.token as string;
    if (!token || !/^[a-f0-9]{32}$/.test(token)) {
      hilog.error(0x0001, 'GoHmosApp', 'Missing or invalid run token');
      return;
    }
    gohmos.run(token).then((report: string) => {
      // Log bounded chunks to avoid hilog's per-message truncation. A fresh
      // host-generated token prevents stale/other-process output from passing.
      const size = 1800;
      const count = Math.ceil(report.length / size);
      for (let i = 0; i < count; i++) {
        hilog.info(0x0001, 'GoHmosApp', 'GO_HMOS_APP_%{public}s_%{public}d_%{public}d:%{public}s',
          token, i, count, report.slice(i * size, (i + 1) * size));
      }
    }).catch((error: Error) => {
      hilog.error(0x0001, 'GoHmosApp', 'GO_HMOS_APP_ERROR_%{public}s:%{public}s', token, error.message);
    });
  }

  onWindowStageCreate(windowStage: window.WindowStage): void {
    windowStage.loadContent('pages/Index');
  }
}
