try:
    import cProfile as profile
except ImportError:
    import profile

try:
    from cStringIO import StringIO
except:
    from io import StringIO

import pstats
from django.db import connections
from django.utils.deprecation import MiddlewareMixin
from django.contrib.admin.views import main
from django.http import HttpResponse

NEW_ADMIN_IGNORED_PARAMS = ('prof', 'prof_db')

# patch django admin to allow profiling query params
if NEW_ADMIN_IGNORED_PARAMS[0] not in main.IGNORED_PARAMS:
    main.IGNORED_PARAMS += NEW_ADMIN_IGNORED_PARAMS


class ProfilerMiddleware(MiddlewareMixin):
    """
    Simple profile middleware to profile django views. To run it, add ?prof to
    the URL like this:

        http://localhost:8000/view/?prof

    Optionally pass the following to modify the output:

    ?sort => Sort the output by a given metric. Default is time.
        See http://docs.python.org/2/library/profile.html#pstats.Stats.sort_stats
        for all sort options.

    ?count => The number of rows to display. Default is 100.

    This is adapted from an example found here:
    http://www.slideshare.net/zeeg/django-con-high-performance-django-presentation.
    """
    def can(self, request):
        return 'prof' in request.GET and \
            request.user is not None and request.user.is_staff

    def can_db(self, request):
        return 'prof_db' in request.GET and \
               request.user is not None and request.user.is_staff

    def process_view(self, request, callback, callback_args, callback_kwargs):
        if self.can(request):
            self.profiler = profile.Profile()
            args = (request,) + callback_args
            try:
                return self.profiler.runcall(callback, *args, **callback_kwargs)
            except:
                # we want the process_exception middleware to fire
                # https://code.djangoproject.com/ticket/12250
                return

    def process_response(self, request, response):
        if self.can(request):
            self.profiler.create_stats()
            io = StringIO()
            stats = pstats.Stats(self.profiler, stream=io)
            stats.strip_dirs().sort_stats(request.GET.get('sort', 'time'))
            stats.print_stats(int(request.GET.get('count', 100)))
            content = '<pre>%s</pre>' % io.getvalue()
            return HttpResponse(content)

        elif self.can_db(request):
            sqltime = 0.0
            num = 0
            content = []
            for db in connections.databases.keys():
                queries = connections[db].queries
                if not len(queries):
                    continue

                content.append('Database: %s' % db)
                for q in queries:
                    num += 1
                    sqltime += float(q['time'])
                    content.append('%d %ss %s' % (num, q['time'], q['sql']))
                    
            content.insert(0, "Total: %dms Count: %d" % (sqltime * 1000, num))
            content = '<code>\n%s\n</code>' % '<hr>\n\n'.join(content)
            return HttpResponse(content)

        return response
