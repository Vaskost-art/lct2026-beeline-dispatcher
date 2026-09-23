import type { Meta, PlanPayload } from '../../api/types';
import type { Day } from '../../state/day';
import { CompareDialog } from '../compare/CompareDialog';
import { AssumptionsDialog } from '../data/AssumptionsDialog';
import { UploadDialog } from '../data/UploadDialog';
import { ValidateDialog } from '../data/ValidateDialog';
import { PickupDialog } from '../pickup/PickupDialog';
import { RiskDialog } from '../risk/RiskDialog';
import { ShortfallDialog } from '../shortfall/ShortfallDialog';

/** Окна экрана диспетчера: каждое открывается своей панелью дня. */
export function Dialogs({
  day,
  meta,
  plan: payload,
}: {
  day: Day;
  meta: Meta | undefined;
  plan: PlanPayload | undefined;
}) {
  return (
    <>
    <UploadDialog
      open={day.panel === 'upload'}
      onClose={day.closePanel}
      onLoaded={(region) => {
        day.closePanel();
        day.selectRegion(region);
      }}
    />

    <AssumptionsDialog
      meta={meta}
      open={day.panel === 'assumptions'}
      onClose={day.closePanel}
    />

    {day.region ? (
      <>
        <CompareDialog
          region={day.region}
          open={day.panel === 'compare'}
          onClose={day.closePanel}
        />
        <ValidateDialog
          region={day.region}
          open={day.panel === 'validate'}
          onClose={day.closePanel}
        />
      </>
    ) : null}

    {payload ? (
      <>
        <RiskDialog
            plan={payload}
            open={day.panel === 'risk'}
            onClose={day.closePanel}
            onShowCrew={(crew) => {
              day.closePanel();
              day.showTab('routes');
              day.focusOnCrew(crew);
            }}
          />
        <PickupDialog plan={payload} open={day.panel === 'pickup'} onClose={day.closePanel} />
        <ShortfallDialog
          plan={payload}
          open={day.panel === 'shortfall'}
          onClose={day.closePanel}
          onShowUnassigned={() => {
            day.closePanel();
            day.showUnassigned();
          }}
          onExport={() => {
            if (day.region) window.open(`/api/export/${day.region}`, '_blank');
          }}
        />
      </>
    ) : null}
    </>
  );
}
