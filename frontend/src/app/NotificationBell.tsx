import { Bell } from "lucide-react";
import { useEffect, useRef } from "react";
import { useNavigate } from "react-router";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import type { Notification } from "@/lib/api";
import { formatRelative } from "@/lib/format";
import {
  useMarkAllNotificationsRead,
  useMarkNotificationRead,
  useNotifications,
} from "@/lib/queries";
import { cn } from "@/lib/utils";

/** Bell with an unread badge. Polls the API and toasts notifications that arrive while open. */
export function NotificationBell() {
  const { data } = useNotifications();
  const markRead = useMarkNotificationRead();
  const markAllRead = useMarkAllNotificationsRead();
  const navigate = useNavigate();
  const unread = data?.unread_count ?? 0;
  useToastNewNotifications(data?.items);

  function open(notification: Notification) {
    if (!notification.read_at) markRead.mutate(notification.id);
    if (notification.link) navigate(notification.link);
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          className="relative"
          aria-label={unread ? `Notifications (${unread} unread)` : "Notifications"}
        >
          <Bell aria-hidden />
          {unread > 0 && (
            <span className="absolute -top-0.5 -right-0.5 flex min-w-4 items-center justify-center rounded-full bg-destructive px-1 text-[10px] leading-4 font-semibold text-white">
              {unread > 9 ? "9+" : unread}
            </span>
          )}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-80">
        <DropdownMenuLabel className="flex items-center justify-between">
          Notifications
          {unread > 0 && (
            <Button
              variant="link"
              size="sm"
              className="h-auto p-0 text-xs"
              onClick={() => markAllRead.mutate()}
            >
              Mark all as read
            </Button>
          )}
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        {data?.items.length ? (
          data.items.map((notification) => (
            <DropdownMenuItem
              key={notification.id}
              onSelect={() => open(notification)}
              className="flex items-start gap-2"
            >
              <span
                aria-hidden
                className={cn(
                  "mt-1.5 size-2 shrink-0 rounded-full",
                  notification.read_at ? "bg-transparent" : "bg-primary",
                )}
              />
              <span className="min-w-0 flex-1 space-y-0.5">
                <span className="block truncate font-medium">{notification.title}</span>
                {notification.body && (
                  <span className="block truncate text-xs text-muted-foreground">
                    {notification.body}
                  </span>
                )}
                <span className="block text-xs text-muted-foreground">
                  {formatRelative(notification.created_at)}
                </span>
              </span>
            </DropdownMenuItem>
          ))
        ) : (
          <p className="px-2 py-6 text-center text-sm text-muted-foreground">
            You're all caught up.
          </p>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function useToastNewNotifications(items: Notification[] | undefined) {
  const newestSeen = useRef<number | null>(null);
  useEffect(() => {
    if (!items) return;
    const newest = Math.max(0, ...items.map((item) => item.id));
    if (newestSeen.current !== null) {
      items
        .filter((item) => item.id > (newestSeen.current ?? 0) && !item.read_at)
        .forEach((item) => toast(item.title, { description: item.body ?? undefined }));
    }
    newestSeen.current = Math.max(newestSeen.current ?? 0, newest);
  }, [items]);
}
