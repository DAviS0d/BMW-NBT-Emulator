precision mediump float;

uniform sampler2D tex0;
varying mediump vec2 varCoord;
varying mediump vec3 co;
uniform float oparam0;

// oparam0 ... opacity

void main()
{
	vec4 sample = texture2D(tex0, varCoord);
	gl_FragColor = vec4(co, sample.b * oparam0);
}