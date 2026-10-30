precision mediump float;
varying mediump vec3 ReflectDir;
varying mediump vec2 varCoord;

uniform mediump float oparam0;
varying mediump float ambient;
varying mediump float vcolors;

#define RGB(r,g,b) vec3(r/255., g/255., b/255.)

void main()
{ 
	// AMBIENT
	vec3 base_color = RGB(173., 53., 24.); 
	vec3 ambientColor = base_color * ambient;
	
	// SPECULAR
	vec3 specular_light = normalize(vec3(0.,-2., 12.));
	float specular_vec = clamp(dot(specular_light, ReflectDir),0. ,1.); //
	float specular = pow(specular_vec * 1.06, 5.);
	vec3 specular_color = RGB(100., 100., 100.);
	
	gl_FragColor.rgb = ambientColor.rgb;
	gl_FragColor.rgb += (specular * specular_color);
	gl_FragColor.a = oparam0 * varCoord.x *varCoord.x*0.6;
	gl_FragColor.a -= vcolors;
}